"""
Tagessimulation: lädt die Kette der Delta-Jobs Tag für Tag bis zu einer Lade-ID.

Ein „Tag" ist ein Ladelauf der Quelle (Lade-ID). Für jeden Tag laufen alle
beteiligten Jobs einmal in Abhängigkeitsreihenfolge:

- Jobs mit Obergrenze (Steps mit MAX_LOAD_ID, z. B. RAW→DISC) laden bis zur
  Lade-ID des Tages; ihr Ladestand rückt bis dorthin vor (confirm_load_state).
- Folge-Jobs (Steps mit LOAD_CAP, z. B. DISC→REUS) laden ohne Vorgabe bis zum
  kleinsten Ladestand ihrer Vorgänger.

Reihenfolge aus den Metadaten, ohne feste Job-Listen:
- LOAD_CAP nennt die Vorgänger-Jobs („ETL_JOB_ID IN (…)").
- Ein Job, der eine Schlüsseltabelle befüllt (Parameter KEY_TABLE), läuft vor
  den Jobs, die darauf verweisen (fk_definitions → key_table).
Bei gleichem Rang zuerst Jobs mit Obergrenze, dann nach Job-ID.

Je Umgebung läuft höchstens eine Simulation; sie läuft in einem eigenen Thread
mit eigener ETLService-Instanz (eigene Verbindungen) und bricht beim ersten
fehlgeschlagenen Job ab. Der Zustand liegt im Speicher; die Läufe selbst stehen
wie immer in META_ETL_JOB_RUN.
"""

import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import META_SCHEMA, get_active_env_id, get_etl_jobs_path, set_active_env_id
from .template_engine import resolve_step_parameters

logger = logging.getLogger(__name__)

_IN_RE = re.compile(r"ETL_JOB_ID\s+IN\s*\(([\d\s,]+)\)", re.I)

_LOCK = threading.Lock()
_STATUS: Dict[str, Dict[str, Any]] = {}     # je Umgebung
_STOP: Dict[str, threading.Event] = {}


def _key_tables(params: dict) -> List[str]:
    """key_table-Verweise aus fk_definitions (Liste von Dicts, Groß-/Kleinschreibung egal)."""
    out = []
    for k, v in params.items():
        if k.lower() == 'fk_definitions' and isinstance(v, list):
            out += [str(d.get('key_table', '')).upper() for d in v if isinstance(d, dict) and d.get('key_table')]
    return out


def plan(etl_service) -> List[Dict[str, Any]]:
    """Beteiligte Jobs in Ausführungsreihenfolge:
    [{job_id, job_name, obergrenze, vorgaenger: [job_id]}]."""
    conn = etl_service._get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT s.etl_job_step_id, s.etl_job_id, TRIM(j.job_name), s.parameters
            FROM {META_SCHEMA}.META_ETL_JOB_STEP s
            JOIN {META_SCHEMA}.META_ETL_JOB j ON j.etl_job_id = s.etl_job_id
            WHERE s.is_active = 'Y' AND j.is_active = 'Y'
            ORDER BY s.etl_job_id, s.step_order
        """)
        zeilen = cur.fetchall()
    finally:
        conn.close()

    jobs: Dict[int, dict] = {}
    for step_id, job_id, job_name, db_params in zeilen:
        params = resolve_step_parameters(job_id, step_id, db_params, get_etl_jobs_path())
        j = jobs.setdefault(job_id, {'job_id': job_id, 'job_name': job_name, 'obergrenze': False,
                                     'folgejob': False, 'cap': set(), 'liefert': set(), 'braucht': set()})
        if 'MAX_LOAD_ID' in params:
            j['obergrenze'] = True
        cap = params.get('LOAD_CAP')
        if isinstance(cap, str):
            j['folgejob'] = True
            for m in _IN_RE.finditer(cap):
                j['cap'] |= {int(x) for x in m.group(1).replace(' ', '').split(',') if x}
        if isinstance(params.get('KEY_TABLE'), str):
            j['liefert'].add(params['KEY_TABLE'].upper())
        j['braucht'] |= set(_key_tables(params))

    beteiligt = {k: v for k, v in jobs.items() if v['obergrenze'] or v['folgejob']}
    liefernd = {t: k for k, v in beteiligt.items() for t in v['liefert']}
    for k, v in beteiligt.items():
        v['vorgaenger'] = sorted(({x for x in v['cap'] if x in beteiligt}
                                  | {liefernd[t] for t in v['braucht'] if t in liefernd}) - {k})

    # Topologisch sortieren (Kahn), bei gleichem Rang Jobs mit Obergrenze zuerst, dann Job-ID
    offen = {k: set(v['vorgaenger']) for k, v in beteiligt.items()}
    rang = lambda k: (0 if beteiligt[k]['obergrenze'] else 1, k)
    folge = []
    while offen:
        bereit = sorted((k for k, vs in offen.items() if not vs), key=rang)
        if not bereit:
            raise ValueError(f"Zyklische Abhängigkeit zwischen den Jobs {sorted(offen)}")
        k = bereit[0]
        folge.append(k)
        del offen[k]
        for vs in offen.values():
            vs.discard(k)
    return [{'job_id': k, 'job_name': beteiligt[k]['job_name'], 'obergrenze': beteiligt[k]['obergrenze'],
             'vorgaenger': beteiligt[k]['vorgaenger']} for k in folge]


def status(env_id: Optional[str] = None, max_laeufe: int = 200) -> Dict[str, Any]:
    """Zustand der Simulation; von den Läufen nur die letzten max_laeufe."""
    st = dict(_STATUS.get(env_id or get_active_env_id(), {'zustand': 'bereit'}))
    laeufe = st.get('laeufe') or []
    st['anzahl_laeufe'] = len(laeufe)
    st['laeufe'] = laeufe[-max_laeufe:]
    return st


def tage(lade_ids: List[int], ladestand: Optional[int], bis: int, tag_fuer_tag: bool) -> List[int]:
    """Zu ladende Tage: die Lade-IDs über dem Ladestand bis einschließlich „bis"
    (Tag für Tag) oder nur „bis" (ein Lauf)."""
    if ladestand is not None and bis <= ladestand:
        return []
    if not tag_fuer_tag:
        return [bis]
    return [i for i in lade_ids if (ladestand is None or i > ladestand) and i <= bis]


def start(etl_service_cls, bis: int, tag_fuer_tag: bool = True) -> Dict[str, Any]:
    """Startet die Simulation im Hintergrund; Fehler, wenn schon eine läuft."""
    env_id = get_active_env_id()
    with _LOCK:
        if _STATUS.get(env_id, {}).get('zustand') == 'laeuft':
            raise RuntimeError("In dieser Umgebung läuft bereits eine Simulation.")
        svc = etl_service_cls()
        folge = plan(svc)
        daten = svc.get_load_ids()
        staende = {j['job_id']: j['ladestand'] for j in daten['jobs']}
        grenzjobs = [j for j in folge if j['obergrenze']]
        if not grenzjobs:
            raise ValueError("Keine Jobs mit Obergrenze (MAX_LOAD_ID) gefunden.")
        werte = [staende.get(j['job_id']) for j in grenzjobs]
        ladestand = None if any(w is None for w in werte) else min(werte)
        plan_tage = tage([l['lade_id'] for l in daten['lade_ids']], ladestand, bis, tag_fuer_tag)
        if not plan_tage:
            raise ValueError(f"Nichts zu laden: Ladestand der Kette ist {ladestand}, gewählt bis {bis}.")
        stop = threading.Event()
        _STOP[env_id] = stop
        _STATUS[env_id] = {
            'zustand': 'laeuft', 'bis': bis, 'tag_fuer_tag': tag_fuer_tag,
            'ladestand_vorher': ladestand, 'tage': plan_tage, 'tag': None, 'tag_nr': 0,
            'jobs_je_tag': len(folge), 'job_nr': 0, 'job': None,
            'gestartet': datetime.now(), 'beendet': None, 'meldung': None, 'laeufe': [],
        }
    t = threading.Thread(target=_lauf, args=(env_id, etl_service_cls, svc, folge, plan_tage, stop),
                         name=f"tagessimulation-{env_id}", daemon=True)
    t.start()
    return status(env_id)


def stop(env_id: Optional[str] = None) -> Dict[str, Any]:
    """Hält nach dem laufenden Job an."""
    env_id = env_id or get_active_env_id()
    ev = _STOP.get(env_id)
    if ev and _STATUS.get(env_id, {}).get('zustand') == 'laeuft':
        ev.set()
        _STATUS[env_id]['meldung'] = 'Wird nach dem laufenden Job angehalten …'
    return status(env_id)


def _run_status(svc, run_id: int) -> str:
    conn = svc._get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT TRIM(status) FROM {META_SCHEMA}.META_ETL_JOB_RUN WHERE etl_job_run_id = ?", (run_id,))
        r = cur.fetchone()
        return r[0] if r else 'UNBEKANNT'
    finally:
        conn.close()


def _lauf(env_id, etl_service_cls, svc, folge, plan_tage, stop_ev):
    set_active_env_id(env_id)          # eigener Thread: Umgebung neu setzen
    st = _STATUS[env_id]
    try:
        for tag_nr, tag in enumerate(plan_tage, 1):
            st.update(tag=tag, tag_nr=tag_nr)
            for job_nr, job in enumerate(folge, 1):
                if stop_ev.is_set():
                    st.update(zustand='angehalten', meldung=f"Angehalten vor Tag {tag}, Job {job['job_id']}.")
                    return
                st.update(job_nr=job_nr, job=job['job_id'])
                t0 = time.time()
                bis = tag if job['obergrenze'] else None
                eintrag = {'tag': tag, 'job_id': job['job_id'], 'bis': bis}
                try:
                    run_id = svc.orchestrator.execute_job(job['job_id'], execution_mode='SCHEDULED',
                                                          max_load_id=bis)
                    eintrag.update(run_id=run_id, status=_run_status(svc, run_id))
                except Exception as e:
                    eintrag.update(run_id=None, status='FAILED', fehler=str(e)[:500])
                eintrag['dauer_s'] = round(time.time() - t0, 1)
                st['laeufe'].append(eintrag)
                if eintrag['status'] != 'SUCCESS':
                    st.update(zustand='fehler',
                              meldung=f"Job {job['job_id']} ({job['job_name']}) an Tag {tag}: {eintrag['status']}. "
                                      f"Simulation abgebrochen.")
                    return
        st.update(zustand='fertig', meldung=f"{len(plan_tage)} Tag(e) geladen, bis Lade-ID {plan_tage[-1]}.")
    except Exception as e:
        logger.exception("Tagessimulation abgebrochen")
        st.update(zustand='fehler', meldung=f"Abbruch: {e}")
    finally:
        st['beendet'] = datetime.now()
        st['job'] = None
