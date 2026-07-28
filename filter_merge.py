
import pandas as pd
import os

# Paths
dir_path = r"D:\工具\脆弱性打分\reg-finder\output"
csv1_path = os.path.join(dir_path, "1.csv")
csv2_path = os.path.join(dir_path, "2.csv")
xlsx_path = os.path.join(dir_path, "results_filtered.xlsx")

# --- Read CSV files ---
df1 = pd.read_csv(csv1_path)
df2 = pd.read_csv(csv2_path)

# Normalize column names (strip whitespace)
df1.columns = df1.columns.str.strip()
df2.columns = df2.columns.str.strip()

print(f"1.csv total rows: {len(df1)}")
print(f"2.csv total rows: {len(df2)}")

# Filter: 得分 > 5
df1_filtered = df1[df1["得分"] > 5].copy()
df2_filtered = df2[df2["得分"] > 5].copy()

print(f"1.csv rows with score > 5: {len(df1_filtered)}")
print(f"2.csv rows with score > 5: {len(df2_filtered)}")

# Combine filtered data
df_new = pd.concat([df1_filtered, df2_filtered], ignore_index=True)
print(f"Combined filtered rows: {len(df_new)}")

# --- Read existing xlsx (if exists) ---
if os.path.exists(xlsx_path):
    df_existing = pd.read_excel(xlsx_path)
    df_existing.columns = df_existing.columns.str.strip()
    print(f"Existing xlsx rows: {len(df_existing)}")
else:
    df_existing = pd.DataFrame(columns=df1.columns)
    print("No existing xlsx found, will create new.")

# Deduplicate by URL (keep first occurrence from existing, then append new unique URLs)
# Combine: existing first, then new rows that don't exist in existing by URL
url_col = "URL"
if url_col in df_existing.columns and url_col in df_new.columns:
    existing_urls = set(df_existing[url_col].dropna().astype(str))
    df_new_unique = df_new[~df_new[url_col].astype(str).isin(existing_urls)].copy()
    print(f"New unique rows (not already in xlsx): {len(df_new_unique)}")

    df_final = pd.concat([df_existing, df_new_unique], ignore_index=True)
else:
    df_final = df_new
    print("URL column not found in both files, appending all.")

# Write back
df_final.to_excel(xlsx_path, index=False, engine="openpyxl")
print(f"Done! Total rows in results_filtered.xlsx: {len(df_final)}")
