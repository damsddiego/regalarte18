-- Read-only checks before upgrading sng_cycle_count to 18.0.3.0.0.
BEGIN READ ONLY;

SELECT w.id AS warehouse_id, w.name AS bodega,
       count(DISTINCT c.id) AS sesiones_abiertas,
       count(DISTINCT c.id) FILTER (WHERE c.user_id IS NOT NULL) AS asignadas
FROM sng_cycle_count c
JOIN sng_cycle_count_line l ON l.cycle_count_id = c.id
JOIN stock_location loc ON loc.id = l.location_id
LEFT JOIN stock_warehouse w ON w.id = loc.warehouse_id
WHERE c.state IN ('draft', 'in_progress', 'pending_review', 'pending_approval')
GROUP BY w.id, w.name ORDER BY w.id;

SELECT c.id, c.name, c.state,
       count(l.id) AS lineas,
       count(DISTINCT loc.warehouse_id) AS bodegas,
       count(l.id) FILTER (WHERE loc.warehouse_id IS NULL) AS lineas_sin_bodega
FROM sng_cycle_count c
LEFT JOIN sng_cycle_count_line l ON l.cycle_count_id = c.id
LEFT JOIN stock_location loc ON loc.id = l.location_id
WHERE c.state IN ('draft', 'in_progress', 'pending_review', 'pending_approval')
GROUP BY c.id HAVING count(DISTINCT loc.warehouse_id) != 1
                    OR count(l.id) FILTER (WHERE loc.warehouse_id IS NULL) > 0
ORDER BY c.id;

SELECT l.quant_id, array_agg(l.cycle_count_id ORDER BY l.cycle_count_id) AS sesiones_duplicadas
FROM sng_cycle_count_line l JOIN sng_cycle_count c ON c.id = l.cycle_count_id
WHERE c.state IN ('draft', 'in_progress', 'pending_review', 'pending_approval')
GROUP BY l.quant_id HAVING count(*) > 1;

SELECT r.id AS solicitud_manual, l.cycle_count_id AS sesion, l.quant_id
FROM sng_inventory_adjustment_request r
JOIN sng_cycle_count_line l ON l.quant_id = r.quant_id
JOIN sng_cycle_count c ON c.id = l.cycle_count_id
WHERE r.state IN ('draft', 'pending')
  AND c.state IN ('draft', 'in_progress', 'pending_review', 'pending_approval');

SELECT calendar_id, company_id, count(*) AS dias_no_laborables_configurados,
       min(date_from) AS primero, max(date_to) AS ultimo
FROM resource_calendar_leaves
WHERE resource_id IS NULL AND date_to >= CURRENT_TIMESTAMP
GROUP BY calendar_id, company_id;

ROLLBACK;
