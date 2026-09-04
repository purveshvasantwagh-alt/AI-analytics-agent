import os
import re
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv(override=True)

# Streamlit Page Setup
st.set_page_config(page_title="Conversational AI Analytics Engine", layout="wide")
st.title("📊 Conversational AI Analytics Engine")
st.write("Query enterprise database records in plain English.")

# API Key Resolution (Environment Variable or Streamlit Secrets)
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not groq_api_key:
    st.error("GROQ_API_KEY is missing. Please add it to your .env file or Streamlit secrets.")
    st.stop()

# Candidate Models (Ordered by reliability & rate limits)
candidate_models = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.6-27b",
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

# Database Initialization
@st.cache_resource
def init_db():
    conn = duckdb.connect(database=':memory:', read_only=False)
    conn.execute("CREATE TABLE IF NOT EXISTS subscriptions AS SELECT * FROM read_csv_auto('subscriptions.csv');")
    return conn

conn = init_db()

def get_db_schema():
    schema_info = conn.execute("DESCRIBE subscriptions;").fetchall()
    schema_str = "Table: subscriptions\nColumns:\n"
    for col in schema_info:
        schema_str += f"- {col[0]} ({col[1]})\n"
    return schema_str

schema = get_db_schema()

def clean_sql_output(raw_text):
    """Strips thinking tags, markdown syntax, and conversational boilerplate."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if sql_match:
        cleaned = sql_match.group(1)
    cleaned = cleaned.replace("```sql", "").replace("```", "").strip()
    return cleaned

def generate_sql_with_retry(user_prompt, schema_text, max_retries=3):
    error_msg = ""
    last_raw_response = ""
    for attempt in range(max_retries):
        prompt = f"""
You are an expert SQL engineer. Convert the user's natural language question into a valid DuckDB SQL query.

{schema_text}

CRITICAL RULES:
1. Respond ONLY with the executable DuckDB SQL statement.
2. Do NOT write explanations, intros, or wrapping text.
3. Query the 'subscriptions' table.

User Question: {user_prompt}
"""
        if error_msg:
            prompt += f"\n\nYour previous SQL attempt failed with error: {error_msg}. Correct the syntax and return ONLY valid SQL."

        try:
            raw_response = llm.invoke(prompt).content
            last_raw_response = raw_response
            cleaned_sql = clean_sql_output(raw_response)
            df = conn.execute(cleaned_sql).fetchdf()
            return df, cleaned_sql, attempt + 1, None
        except Exception as e:
            error_msg = str(e)

    return None, last_raw_response, max_retries, error_msg

# Initialize session state for user input persistence
if "user_query" not in st.session_state:
    st.session_state.user_query = ""

# Sample Queries Selection
st.write("💡 **Sample Queries (click to select):**")
col1, col2, col3 = st.columns(3)

if col1.button("📊 Total Revenue by Plan"):
    st.session_state.user_query = "Show total monthly price by plan"
if col2.button("👥 Active Subscriptions"):
    st.session_state.user_query = "Show count of active subscriptions grouped by plan"
if col3.button("❌ Cancelled Users"):
    st.session_state.user_query = "List all cancelled subscriptions sorted by signup date"

user_query = st.text_input(
    "Ask a question about your data:",
    key="user_query",
    placeholder="e.g., Show total monthly price by plan"
)

# Execution Logic
if st.button("Submit Query") and st.session_state.user_query:
    with st.spinner("Generating SQL query & executing analytics..."):
        df, final_sql, attempts, last_err = generate_sql_with_retry(st.session_state.user_query, schema)

        if df is not None:
            st.success(f"Query executed successfully in {attempts} attempt(s)!")

            with st.expander("View Generated SQL Query", expanded=False):
                st.code(final_sql, language="sql")

            res_col1, res_col2 = st.columns([1, 1])

            with res_col1:
                st.subheader("Data Table")
                st.dataframe(df, use_container_width=True)

            with res_col2:
                st.subheader("Automated Visualization")
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()

                if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                    fig = px.bar(
                        df,
                        x=categorical_cols[0],
                        y=numeric_cols[0],
                        title=f"{numeric_cols[0]} by {categorical_cols[0]}"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Insufficient numeric/categorical dimensions for auto-chart plotting.")

            st.divider()
            st.subheader("🤖 AI Executive Insights")
            summary_prompt = f"Analyze this data output and provide 3 short, high-impact bullet points for executive leadership:\nData:\n{df.to_string()}"
            with st.spinner("Generating executive insights..."):
                summary = llm.invoke(summary_prompt).content
            st.write(summary)

        else:
            st.error("Failed to execute SQL after self-healing attempts.")
            with st.expander("Debug Details"):
                st.write("**DuckDB Execution Error:**")
                st.code(last_err)
                st.write("**Raw LLM Output:**")
                st.code(final_sql)