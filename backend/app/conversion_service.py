"""
SQL Dialect Conversion Service
Converts SQL from one dialect to another using sqlglot and provides LLM-based review
"""
import os
import yaml
import sqlglot
import httpx
from typing import List, Dict, Optional, Any
from pathlib import Path

# Get the config directory
CONFIG_DIR = Path(__file__).parent.parent / "config"
CONVERSION_CONFIG_PATH = CONFIG_DIR / "conversion_config.yaml"


class ConversionConfig:
    """Manages conversion configuration from YAML"""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load conversion configuration from YAML file"""
        if not CONVERSION_CONFIG_PATH.exists():
            # Return default config if file doesn't exist
            return {
                "allowed_target_dialects": ["teradata"],
                "default_target_dialect": "teradata",
                "llm_review_enabled": True,
                "llm_review_prompt": "Review this SQL code.",
                "llm_review_max_tokens": 1000,
                "llm_review_timeout": 60
            }
        
        with open(CONVERSION_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @property
    def allowed_target_dialects(self) -> List[str]:
        """Get list of allowed target dialects"""
        return self.config.get("allowed_target_dialects", ["teradata"])
    
    @property
    def default_target_dialect(self) -> str:
        """Get default target dialect"""
        return self.config.get("default_target_dialect", "teradata")
    
    @property
    def llm_review_enabled(self) -> bool:
        """Check if LLM review is enabled"""
        return self.config.get("llm_review_enabled", True)
    
    @property
    def llm_review_prompt(self) -> str:
        """Get LLM review prompt template"""
        return self.config.get("llm_review_prompt", "Review this SQL code.")
    
    @property
    def llm_review_max_tokens(self) -> int:
        """Get max tokens for LLM review"""
        return self.config.get("llm_review_max_tokens", 1000)
    
    @property
    def llm_review_timeout(self) -> int:
        """Get timeout for LLM review"""
        return self.config.get("llm_review_timeout", 60)


class ConversionService:
    """Service for SQL dialect conversion and LLM review"""
    
    def __init__(self):
        self.config = ConversionConfig()
    
    def convert_sql(
        self,
        sql: str,
        source_dialect: str,
        target_dialect: str,
        llm_connection: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convert SQL from source dialect to target dialect
        
        Args:
            sql: SQL code to convert
            source_dialect: Source SQL dialect (e.g., 'tsql', 'postgres')
            target_dialect: Target SQL dialect (e.g., 'teradata')
            llm_connection: Optional LLM connection for review
        
        Returns:
            Dictionary with conversion results and optional LLM review
        """
        result = {
            "success": False,
            "source_dialect": source_dialect,
            "target_dialect": target_dialect,
            "original_sql": sql,
            "converted_sql": None,
            "llm_reviews": [],
            "error": None,
            "stats": {
                "original_lines": len(sql.strip().split('\n')),
                "converted_lines": 0,
                "conversion_time_ms": 0
            }
        }
        
        try:
            # Validate target dialect is allowed
            if target_dialect not in self.config.allowed_target_dialects:
                raise ValueError(
                    f"Target dialect '{target_dialect}' not allowed. "
                    f"Allowed: {', '.join(self.config.allowed_target_dialects)}"
                )
            
            # Clean SQL (remove GO statements for TSQL)
            sql_clean = sql.strip()
            if source_dialect.lower() == 'tsql':
                sql_clean = sql_clean.replace('GO', '').replace('go', '').strip()
            
            # Convert SQL using sqlglot
            import time
            start_time = time.time()
            
            converted = sqlglot.transpile(
                sql_clean,
                read=source_dialect,
                write=target_dialect,
                pretty=True
            )
            
            conversion_time = int((time.time() - start_time) * 1000)
            
            if not converted:
                raise ValueError("SQL conversion failed - no output generated")
            
            # Join multiple statements if any
            converted_sql = '\n\n'.join(converted)
            
            result["converted_sql"] = converted_sql
            result["success"] = True
            result["stats"]["converted_lines"] = len(converted_sql.strip().split('\n'))
            result["stats"]["conversion_time_ms"] = conversion_time
            
            # Get LLM review if enabled and connection provided
            if self.config.llm_review_enabled and llm_connection:
                llm_reviews = self._get_llm_reviews(
                    sql_clean,
                    converted_sql,
                    source_dialect,
                    target_dialect,
                    [llm_connection]  # Can be expanded to multiple LLMs
                )
                result["llm_reviews"] = llm_reviews
        
        except Exception as e:
            result["error"] = str(e)
            result["success"] = False
        
        return result
    
    def _get_llm_reviews(
        self,
        original_sql: str,
        converted_sql: str,
        source_dialect: str,
        target_dialect: str,
        llm_connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Get LLM reviews for converted SQL
        
        Args:
            original_sql: Original SQL before conversion
            converted_sql: Converted SQL
            source_dialect: Source dialect
            target_dialect: Target dialect
            llm_connections: List of LLM connection configurations
        
        Returns:
            List of review results
        """
        reviews = []
        
        for conn in llm_connections:
            try:
                # Format prompt with conversion context
                prompt = self.config.llm_review_prompt.format(
                    source_dialect=source_dialect.upper(),
                    target_dialect=target_dialect.upper(),
                    converted_sql=converted_sql
                )
                
                # Call LLM based on backend type
                backend_type = conn.get('backend_type', 'ollama')
                
                if backend_type == 'ollama':
                    review_text = self._call_ollama(
                        conn['url'],
                        conn['model'],
                        prompt,
                        self.config.llm_review_max_tokens,
                        self.config.llm_review_timeout
                    )
                else:  # openai-compatible (llm-farm)
                    review_text = self._call_openai_compatible(
                        conn['url'],
                        conn['model'],
                        prompt,
                        self.config.llm_review_max_tokens,
                        self.config.llm_review_timeout,
                        conn.get('api_key')
                    )
                
                # Filter DeepSeek R1 thinking tags if present
                if 'deepseek' in conn['model'].lower() or 'r1' in conn['model'].lower():
                    if '</think>' in review_text:
                        parts = review_text.split('</think>')
                        review_text = parts[-1].strip()
                
                reviews.append({
                    "llm_name": conn['name'],
                    "llm_model": conn['model'],
                    "review": review_text,
                    "success": True,
                    "error": None
                })
            
            except Exception as e:
                reviews.append({
                    "llm_name": conn.get('name', 'Unknown'),
                    "llm_model": conn.get('model', 'Unknown'),
                    "review": None,
                    "success": False,
                    "error": str(e)
                })
        
        return reviews
    
    def _call_ollama(
        self,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout: int
    ) -> str:
        """Call Ollama API for LLM review"""
        url = f"{base_url.rstrip('/')}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.3
            }
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get('response', '').strip()
    
    def _call_openai_compatible(
        self,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout: int,
        api_key: Optional[str] = None
    ) -> str:
        """Call OpenAI-compatible API (llm-farm) for LLM review"""
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a SQL expert specializing in database dialect conversion and optimization."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if 'choices' in data and len(data['choices']) > 0:
                return data['choices'][0]['message']['content'].strip()
            
            return ""


# Global service instance
conversion_service = ConversionService()
