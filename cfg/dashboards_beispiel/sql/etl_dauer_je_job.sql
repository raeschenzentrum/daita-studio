LOCKING ROW FOR ACCESS
SELECT TOP 15
    j.job_name                                      AS JOB_NAME,
    CAST(AVG(r.duration_seconds) AS DECIMAL(12,1))  AS DAUER_AVG_S
FROM ${META_SCHEMA}.META_ETL_JOB_RUN r
JOIN ${META_SCHEMA}.META_ETL_JOB j ON j.etl_job_id = r.etl_job_id
WHERE CAST(r.start_time AS DATE) >= CURRENT_DATE - ${FILTER:tage}
  AND r.status = 'SUCCESS'
GROUP BY 1
ORDER BY 2 DESC
