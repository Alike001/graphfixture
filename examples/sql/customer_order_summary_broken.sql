SELECT
    c.customer_id,
    c.name,
    COUNT(DISTINCT o.order_id) AS order_count
FROM customers AS c
INNER JOIN orders AS o ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi ON oi.order_id = o.order_id
WHERE c.status = 'active'
GROUP BY c.customer_id, c.name
ORDER BY c.customer_id;
