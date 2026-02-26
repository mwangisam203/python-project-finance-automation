import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os

st.set_page_config(page_title="My Ideal Finance App", page_icon="💰💰😎", layout="wide")

CATEGORY_FILE = "categories.json"

# Categories: load/save
def default_categories():
    return {"Uncategorized": []}


def load_categories():
    if os.path.exists(CATEGORY_FILE):
        try:
            with open(CATEGORY_FILE, "r") as f:
                data = json.load(f)
            # Ensure it's a dict and has Uncategorized
            if isinstance(data, dict):
                data.setdefault("Uncategorized", [])
                return data
        except Exception:
            pass
    return default_categories()


def save_categories():
    with open(CATEGORY_FILE, "w") as f:
        json.dump(st.session_state.categories, f, indent=2)


if "categories" not in st.session_state:
    st.session_state.categories = load_categories()


# Categorization

def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Category"] = "Uncategorized"

    # Build lowercase keywords per category
    keyword_map = {}
    for category, keywords in st.session_state.categories.items():
        if category == "Uncategorized" or not keywords:
            continue
        keyword_map[category] = [k.lower().strip() for k in keywords if k and k.strip()]

    # Assign categories (simple substring match)
    for idx, row in df.iterrows():
        details = str(row.get("Details", "")).lower().strip()
        if not details:
            continue

        assigned = False
        for category, lowered_keywords in keyword_map.items():
            for kw in lowered_keywords:
                if kw and kw in details:
                    df.at[idx, "Category"] = category
                    assigned = True
                    break
            if assigned:
                break

    return df


def load_transactions(file) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(file)
        df.columns = [col.strip() for col in df.columns]

        required_cols = {"Date", "Details", "Amount", "Debit/Credit"}
        missing = required_cols - set(df.columns)
        if missing:
            st.error(f"Missing required columns: {', '.join(sorted(missing))}")
            return None

        # Clean and parse
        df["Amount"] = df["Amount"].astype(str).str.replace(",", "", regex=False).astype(float)
        df["Date"] = pd.to_datetime(df["Date"], format="%d %b %Y", errors="coerce")

        # Drop rows with bad dates
        df = df.dropna(subset=["Date"])

        return categorize_transactions(df)

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None


def add_keyword_to_category(category: str, keyword: str) -> bool:
    keyword = (keyword or "").strip()
    if not keyword:
        return False

    st.session_state.categories.setdefault(category, [])
    if keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False



# App UI

def main():
    st.title("My Xpress € 💶 Dashboard")

    uploaded_file = st.file_uploader("Upload your transaction file", type=["csv"])

    if uploaded_file is None:
        st.info("Upload a CSV to get started.")
        return

    df = load_transactions(uploaded_file)
    if df is None or df.empty:
        st.warning("No transactions found or file could not be processed.")
        return

    debits_df = df[df["Debit/Credit"].str.strip().str.lower() == "debit"].copy()
    credits_df = df[df["Debit/Credit"].str.strip().str.lower() == "credit"].copy()

    # Keep expenses in session for editing
    st.session_state.debits_df = debits_df.copy()

    # --- Sidebar Filters ---
    st.sidebar.header("Filters")

    min_date = df["Date"].min().date()
    max_date = df["Date"].max().date()
    date_range = st.sidebar.date_input("Date range", (min_date, max_date))

    search = st.sidebar.text_input("Search Details (optional)").strip().lower()

    all_categories = list(st.session_state.categories.keys())
    selected_categories = st.sidebar.multiselect(
        "Categories",
        options=all_categories,
        default=all_categories
    )

    # Apply filters to expenses (debits)
    start_date = pd.to_datetime(date_range[0])
    end_date = pd.to_datetime(date_range[1])

    filtered_debits = st.session_state.debits_df[
        (st.session_state.debits_df["Date"] >= start_date) &
        (st.session_state.debits_df["Date"] <= end_date) &
        (st.session_state.debits_df["Category"].isin(selected_categories))
    ].copy()

    if search:
        filtered_debits = filtered_debits[
            filtered_debits["Details"].astype(str).str.lower().str.contains(search, na=False)
        ]

    # --- KPIs ---
    total_expenses = debits_df["Amount"].sum() if not debits_df.empty else 0.0
    total_income = credits_df["Amount"].sum() if not credits_df.empty else 0.0
    net = total_income - total_expenses

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Expenses", f"{total_expenses:,.2f} AED")
    c2.metric("Total Income", f"{total_income:,.2f} AED")
    c3.metric("Net", f"{net:,.2f} AED")

    tab1, tab2 = st.tabs(["Expenses (Debits)", "Payments (Credits)"])

    with tab1:
        st.subheader("Categories")

        colA, colB = st.columns([2, 1])
        with colA:
            new_category = st.text_input("New Category Name", placeholder="e.g. Transport")
        with colB:
            add_button = st.button("Add Category")

        if add_button and new_category:
            new_category = new_category.strip()
            if new_category and new_category not in st.session_state.categories:
                st.session_state.categories[new_category] = []
                save_categories()
                st.success(f"Added a new category: {new_category}")
                st.rerun()

        st.subheader("Your Expenses")

        edited_df = st.data_editor(
            filtered_debits[["Date", "Details", "Amount", "Category"]],
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f AED"),
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=list(st.session_state.categories.keys())
                )
            },
            hide_index=False,  # keep index so we can map back safely
            use_container_width=True,
            key="category_editor"
        )

        save_button = st.button("Apply Changes", type="primary")
        if save_button:
            changes = 0
            for idx, row in edited_df.iterrows():
                new_cat = row["Category"]
                old_cat = st.session_state.debits_df.at[idx, "Category"]
                if new_cat == old_cat:
                    continue

                # Update category in the master expenses df
                st.session_state.debits_df.at[idx, "Category"] = new_cat
                details = str(row["Details"])

                # Learn this detail as a keyword for future auto-categorization
                if add_keyword_to_category(new_cat, details):
                    pass
                changes += 1

            if changes:
                st.success(f"Applied {changes} change(s).")
            else:
                st.info("No changes to apply.")

        st.subheader("Expense Summary")

        # Use the updated master debits_df for summary
        category_totals = st.session_state.debits_df.groupby("Category")["Amount"].sum().reset_index()
        category_totals = category_totals.sort_values("Amount", ascending=False)

        st.dataframe(
            category_totals,
            column_config={"Amount": st.column_config.NumberColumn("Amount", format="%.2f AED")},
            use_container_width=True,
            hide_index=True
        )

        fig = px.pie(category_totals, values="Amount", names="Category", title="Expenses by Category")
        st.plotly_chart(fig, use_container_width=True)

        # Monthly trend
        st.subheader("Monthly Trend")
        monthly = st.session_state.debits_df.copy()
        monthly["Month"] = monthly["Date"].dt.to_period("M").astype(str)
        monthly_totals = monthly.groupby("Month")["Amount"].sum().reset_index()

        fig2 = px.line(monthly_totals, x="Month", y="Amount", title="Monthly Expenses Trend")
        st.plotly_chart(fig2, use_container_width=True)

        # Download
        st.subheader("Export")
        csv_bytes = st.session_state.debits_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Categorized Expenses CSV",
            data=csv_bytes,
            file_name="categorized_expenses.csv",
            mime="text/csv"
        )

    with tab2:
        st.subheader("Payment Summary")
        total_payments = credits_df["Amount"].sum() if not credits_df.empty else 0.0
        st.metric("Total Payments", f"{total_payments:,.2f} AED")

        # Optional: show table with filters too (simple)
        st.dataframe(
            credits_df[["Date", "Details", "Amount", "Debit/Credit"]],
            use_container_width=True,
            hide_index=True
        )


main()