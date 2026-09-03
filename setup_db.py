import duckdb

conn = duckdb.connect("enterprise_data.db")

conn.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    customer_id VARCHAR,
    contract_type VARCHAR,
    monthly_charges DOUBLE,
    tenure_months INT,
    churn_status VARCHAR,
    region VARCHAR
);
""")

conn.execute("""
INSERT INTO subscriptions VALUES 
('C101', 'Month-to-month', 85.50, 4, 'Churned', 'North'),
('C102', 'Two year', 45.00, 36, 'Active', 'East'),
('C103', 'One year', 65.00, 18, 'Active', 'West'),
('C104', 'Month-to-month', 95.00, 2, 'Churned', 'South'),
('C105', 'Month-to-month', 105.00, 6, 'Churned', 'North'),
('C106', 'Two year', 50.00, 48, 'Active', 'West'),
('C107', 'One year', 70.00, 12, 'Active', 'South'),
('C108', 'Month-to-month', 88.00, 1, 'Churned', 'East');
""")

conn.close()
print("Database enterprise_data.db created successfully!")