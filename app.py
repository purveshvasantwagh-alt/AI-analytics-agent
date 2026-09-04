import os
import re
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv(override=True)

st.set_page_config(page_title="Conversational AI Analytics Engine", layout="wide")
st.title("📊 Conversational AI Analytics Engine")
st.write("Query enterprise database records in plain English.")

groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    st.error("GROQ_API_KEY is missing in .env file.")
    st.stop()

candidate_models = [
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound"
]

llm = None
active_model = None

for model_name in candidate_models:
    try:
        temp_llm = ChatGroq(model=model_name, temperature=0, groq_api_key=groq_api_key)
        temp_llm.invoke("test")
        llm = temp_llm
        active_model = model_name
        break
    except Exception:
        continue

if not llm:
    st.error("Could not initialize an active model from your Groq project limits.")
    st.stop()

st.sidebar.success(f"Connected Model: {active_model}")

def get_db_schema():
    conn = duckdb.connect("enterprise_data.db")
    schema_info = conn.execute("DESCRIBE subscriptions;").fetchall()
    conn.close()
    return "Table: subscriptions\nColumns:\n" + "".join([f"- {col[0]} ({col[1]})\n" for col in schema_info])

import duckdb
import streamlit as st

@st.cache_resource
def init_db():
    conn = duckdb.connect(database=':memory:')
    # Load dataset into DuckDB table on startup
    conn.execute("CREATE TABLE IF NOT EXISTS subscriptions AS SELECT * FROM read_csv_auto('subscriptions.csv');")
    return conn

conn = init_db()

def get_db_schema():
    schema_info = conn.execute("DESCRIBE subscriptions;").fetchall()
    return schema_info

schema = get_db_schema()

def clean_sql_output(raw_text):
    """Strips thinking tags, markdown syntax, and conversational boilerplate."""
    # Remove <think>...</think> blocks if present
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
    
    # Extract code inside SQL code blocks if formatted as markdown
    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if sql_match:
        cleaned = sql_match.group(1)
        
    # Remove remaining markdown backticks or extra whitespace
    cleaned = cleaned.replace("```sql", "").replace("```", "").strip()
    return cleaned

def generate_sql_with_retry(user_prompt, schema, max_retries=3):
    error_msg = ""
    last_raw_response = ""
    for attempt in range(max_retries):
        prompt = f"""
You are an expert SQL engineer. Convert the user's natural language question into a valid DuckDB SQL query.

{schema}

CRITICAL RULES:
1. Respond ONLY with the executable DuckDB SQL statement.
2. Do NOT write explanations, intros, or wrapping text.
3. Query the 'subscriptions' table.

User Question: {user_prompt}
"""
        if error_msg:
            prompt += f"\n\nYour previous SQL attempt failed with error: {error_msg}. Correct the syntax and return ONLY valid SQL."
        
        raw_response = llm.invoke(prompt).content
        last_raw_response = raw_response
        cleaned_sql = clean_sql_output(raw_response)
        
        try:
            conn = duckdb.connect("enterprise_data.db")
            df = conn.execute(cleaned_sql).fetchdf()
            conn.close()
            return df, cleaned_sql, attempt + 1, None
        except Exception as e:
            error_msg = str(e)
            
    return None, last_raw_response, max_retries, error_msg

user_query = st.text_input("Ask a question about your data:")

if st.button("Submit Query") and user_query:
    with st.spinner("Generating SQL query..."):
        df, final_sql, attempts, last_err = generate_sql_with_retry(user_query, schema)
        
        if df is not None:
            st.write("### Query Results")
            st.dataframe(df)
            st.code(final_sql, language="sql")
        
        if df is not None:
            st.success(f"Query executed successfully in {attempts} attempt(s)!")
            
            with st.expander("View Generated SQL Query"):
                st.code(final_sql, language="sql")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("Data Table")
                st.dataframe(df, use_container_width=True)
                
            with col2:
                st.subheader("Automated Visualization")
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
                
                if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                    fig = px.bar(df, x=categorical_cols[0], y=numeric_cols[0], title=f"{numeric_cols[0]} by {categorical_cols[0]}")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Insufficient numeric/categorical dimensions for auto-chart plotting.")
            
            st.divider()
            st.subheader("🤖 AI Executive Insights")
            summary_prompt = f"Analyze this data output and provide 3 short, high-impact bullet points for executive leadership:\nData:\n{df.to_string()}"
            summary = llm.invoke(summary_prompt).content
            st.write(summary)
            
        else:
            st.error("Failed to execute SQL after self-healing attempts.")
            with st.expander("Debug Details"):
                st.write("**DuckDB Execution Error:**")
                st.code(last_err)
                st.write("**Raw LLM Output:**")
                st.code(final_sql)