import streamlit as st
from datetime import date
from pydantic import BaseModel, Field, validator
from ulid import ULID
import bcrypt, os, json, pandas as pd
from util.excel_template import export_excel
from typing import Optional
import uuid

# ---- Supabase client (optional) ----
SUPABASE_URL = st.secrets.get("SUPABASE_URL", None)
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", None)
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", None)
APP_ADMIN_EMAILS = [e.strip().lower() for e in st.secrets.get("APP_ADMIN_EMAILS","").split(",") if e.strip()]

if SUPABASE_URL and SUPABASE_ANON_KEY:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    supabase_admin: Optional[Client] = None
    if SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
else:
    supabase = None
    supabase_admin = None
    os.makedirs("data", exist_ok=True)

# ---- Helpers ----
def hash_pwd(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pwd(p, h): return bcrypt.checkpw(p.encode(), h.encode())

def is_admin(email: str):
    if email and email.lower() in APP_ADMIN_EMAILS:
        return True
    return st.session_state.get("role") == "admin"

def get_role_from_query():
    role = st.query_params.get("role", ["user"])[0]
    return role

def ensure_tables_exist():
    # For demo/local mode only
    if not supabase:
        for fname in ["users.jsonl","applicants.jsonl"]:
            path = os.path.join("data", fname)
            if not os.path.exists(path):
                open(path,"w").close()

def save_jsonl(path, obj):
    with open(path,"a") as f:
        f.write(json.dumps(obj, default=str)+"\n")

def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows

# ---- Data model ----
class Applicant(BaseModel):
    region: str
    batch: str
    zone: str
    woreda: str
    kebele: str
    first_name: str
    father_name: str
    grandfather_name: str
    date_of_birth: date
    date_collected: date
    sex: str = Field(pattern="^(m|f)$")
    applicant_address: str
    has_business_license: bool
    trade_license_number: Optional[str] = None
    trade: Optional[str] = None
    registration_number: Optional[str] = None
    tin_number: Optional[str] = None
    date_of_business_license: Optional[date] = None
    enterprise_category: str  # micro, small, medium, startup
    ownership_form: str      # soleproprietorship, partnership, plc
    business_sector: str     # manufacturing, construction, agriculture, mining, service, others
    number_of_owners: int
    owners_names: str
    registered_address: str
    business_premise: str    # rented, applicant_owned, government
    male_employees: int
    female_employees: int
    business_capital_etb: float
    monthly_revenue_etb: float
    annual_revenue_last3: float
    net_profit_last3: float
    financing_required_etb: float
    source_of_repayment: str
    purpose_of_funds: str
    guarantor_first_name: str
    guarantor_father_name: str
    guarantor_grandfather_name: str
    guarantor_phone: str
    guarantor_monthly_income: float
    credit_history: str
    cbe_account_number: str
    cbe_branch: str
    cbe_city: str
    mode_of_finance: str     # conventional, ifb

    @validator("enterprise_category")
    def v1(cls, v):
        if v not in ["micro","small","medium","startup"]:
            raise ValueError("Invalid enterprise category")
        return v

    @validator("ownership_form")
    def v2(cls, v):
        if v not in ["soleproprietorship","partnership","plc"]:
            raise ValueError("Invalid ownership form")
        return v

    @validator("business_sector")
    def v3(cls, v):
        if v not in ["manufacturing","construction","agriculture","mining","service","others"]:
            raise ValueError("Invalid business sector")
        return v

    @validator("business_premise")
    def v4(cls, v):
        if v not in ["rented","applicant_owned","government"]:
            raise ValueError("Invalid business premise")
        return v

    @validator("mode_of_finance")
    def v5(cls, v):
        if v not in ["conventional","ifb"]:
            raise ValueError("Invalid mode of finance")
        return v

# ---- UI ----
st.set_page_config(page_title="EDI Loan Application", layout="wide")

# Logo & Title
col1, col2 = st.columns([1,6])
with col1:
    st.image("assets/logo.png", width=80, caption=None, use_container_width=False, output_format="auto")
with col2:
    st.markdown("### Entrepreneur Development Institution Loan Application Form")

role = get_role_from_query()
st.info(f"You are on the **{'Admin' if role=='admin' else 'Collector'}** portal")

ensure_tables_exist()

# ---- Auth ----
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = "collector"

def login_box():
    st.subheader("Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pwd")
    if st.button("Sign in"):
        if supabase:
            res = supabase.table("users").select("*").eq("email", email).execute()
            rows = res.data or []
        else:
            rows = [r for r in load_jsonl("data/users.jsonl") if r["email"].lower()==email.lower()]
        if not rows:
            st.error("User not found")
        else:
            user = rows[0]
            if check_pwd(password, user["password_hash"]):
                st.session_state.user = {"email": email, "id": user.get("id", str(uuid.uuid4()))}
                st.session_state.role = user.get("role","collector")
                st.experimental_rerun()
            else:
                st.error("Incorrect password")

def admin_create_user_box():
    st.subheader("Create User (Admin)")
    with st.form("create_user"):
        email = st.text_input("Email")
        role_sel = st.selectbox("Role", ["collector","admin"])
        pwd1 = st.text_input("Password", type="password")
        pwd2 = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Create User")
        if submitted:
            if not is_admin(st.session_state.user["email"] if st.session_state.user else ""):
                st.error("Admins only")
            elif pwd1 != pwd2 or len(pwd1) < 6:
                st.error("Passwords must match and be at least 6 chars")
            else:
                rec = {"email": email.lower(), "password_hash": hash_pwd(pwd1), "role": role_sel}
                if supabase_admin:
                    supabase_admin.table("users").insert(rec).execute()
                else:
                    rec["id"] = str(uuid.uuid4())
                    save_jsonl("data/users.jsonl", rec)
                st.success("User created")

if not st.session_state.user:
    login_box()
    st.stop()

st.success(f"Logged in as {st.session_state.user['email']} ({st.session_state.role})")

# ---- Collector page ----
def collector_page():
    st.subheader("New Applicant")
    with st.form("applicant_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        region = c1.text_input("Region*")
        batch = c2.text_input("Batch*")
        zone = c3.text_input("Zone*")
        woreda = c4.text_input("Woreda*")
        kebele = c5.text_input("Kebele*")

        c1,c2,c3 = st.columns(3)
        first_name = c1.text_input("Applicant First Name*")
        father_name = c2.text_input("Father Name*")
        grandfather_name = c3.text_input("Grandfather Name*")

        c1,c2,c3 = st.columns(3)
        dob = c1.date_input("Date of Birth*", value=date(1990,1,1))
        collected = c2.date_input("Date of Data Collected*", value=date.today())
        sex = c3.selectbox("Sex*", ["m","f"], help="m for male, f for female")

        address = st.text_input("Applicant Address (as per Kebele ID)*")

        c1,c2 = st.columns(2)
        has_license = c1.selectbox("Business License?*", ["No","Yes"]) == "Yes"
        date_of_license = c2.date_input("Date of Business License Registration", value=None if not has_license else date.today())

        c1,c2,c3,c4 = st.columns(4)
        trade_license_no = c1.text_input("Trade License Number")
        trade = c2.text_input("Trade")
        reg_no = c3.text_input("Registration Number")
        tin_no = c4.text_input("TIN Number")

        c1,c2,c3 = st.columns(3)
        ent_cat = c1.selectbox("Category of Enterprise*", ["micro","small","medium","startup"])
        owner_form = c2.selectbox("Form of Ownership*", ["soleproprietorship","partnership","plc"])
        sector = c3.selectbox("Business Sector*", ["manufacturing","construction","agriculture","mining","service","others"])

        c1,c2,c3 = st.columns(3)
        owners_n = c1.number_input("Number of Owners*", min_value=1, step=1, value=1)
        owners_names = c2.text_input("Name(s) of Owners*")
        reg_addr = c3.text_input("Registered Address*")

        premise = st.selectbox("Business Premise*", ["rented","applicant_owned","government"])

        c1,c2,c3 = st.columns(3)
        male_emp = c1.number_input("Male Employees*", min_value=0, step=1)
        female_emp = c2.number_input("Female Employees*", min_value=0, step=1)
        # total auto

        c1,c2,c3 = st.columns(3)
        capital = c1.number_input("Business Capital (ETB)*", min_value=0.0, step=100.0, format="%.2f")
        monthly_rev = c2.number_input("Monthly Revenue (ETB)*", min_value=0.0, step=100.0, format="%.2f")
        annual_rev3 = c3.number_input("Annual Revenue (Last 3 years total)*", min_value=0.0, step=100.0, format="%.2f")

        net_profit = st.number_input("Net Profit/Loss (Last 1–3 years)*", step=100.0, format="%.2f")

        c1,c2,c3 = st.columns(3)
        finance_req = c1.number_input("Amount of Financing Required (ETB)*", min_value=0.0, step=100.0, format="%.2f")
        repay_src = c2.text_input("Source of Repayment*")
        fund_purpose = c3.text_input("Purpose of the Funds*")

        st.markdown("**Guarantee Information**")
        c1,c2,c3 = st.columns(3)
        g_fn = c1.text_input("Guarantor First Name*")
        g_fan = c2.text_input("Guarantor Father Name*")
        g_gfn = c3.text_input("Guarantor Grandfather Name*")
        c1,c2 = st.columns(2)
        g_phone = c1.text_input("Guarantor Phone*")
        g_income = c2.number_input("Guarantor Monthly Income (ETB)*", min_value=0.0, step=50.0, format="%.2f")

        st.markdown("**Banking Information**")
        c1,c2,c3,c4,c5 = st.columns(5)
        credit_hist = c1.text_input("Credit History*")
        cbe_acc = c2.text_input("C.B.E Business Current Account Number*")
        cbe_branch = c3.text_input("Branch*")
        cbe_city = c4.text_input("City*")
        mode_fin = c5.selectbox("Mode of Finance*", ["conventional","ifb"])

        submitted = st.form_submit_button("Save Applicant")
        if submitted:
            try:
                Applicant(
                    region=region, batch=batch, zone=zone, woreda=woreda, kebele=kebele,
                    first_name=first_name, father_name=father_name, grandfather_name=grandfather_name,
                    date_of_birth=dob, date_collected=collected, sex=sex, applicant_address=address,
                    has_business_license=has_license, trade_license_number=trade_license_no or None, trade=trade or None,
                    registration_number=reg_no or None, tin_number=tin_no or None, date_of_business_license=date_of_license if has_license else None,
                    enterprise_category=ent_cat, ownership_form=owner_form, business_sector=sector,
                    number_of_owners=int(owners_n), owners_names=owners_names, registered_address=reg_addr,
                    business_premise=premise, male_employees=int(male_emp), female_employees=int(female_emp),
                    business_capital_etb=float(capital), monthly_revenue_etb=float(monthly_rev),
                    annual_revenue_last3=float(annual_rev3), net_profit_last3=float(net_profit),
                    financing_required_etb=float(finance_req), source_of_repayment=repay_src, purpose_of_funds=fund_purpose,
                    guarantor_first_name=g_fn, guarantor_father_name=g_fan, guarantor_grandfather_name=g_gfn,
                    guarantor_phone=g_phone, guarantor_monthly_income=float(g_income),
                    credit_history=credit_hist, cbe_account_number=cbe_acc, cbe_branch=cbe_branch, cbe_city=cbe_city, mode_of_finance=mode_fin
                )
            except Exception as e:
                st.error(f"Missing/invalid fields: {e}")
                st.stop()

            # Build record
            rec = dict(
                id=str(ULID()),
                region=region, batch=batch, zone=zone, woreda=woreda, kebele=kebele,
                first_name=first_name, father_name=father_name, grandfather_name=grandfather_name,
                date_of_birth=str(dob), date_collected=str(collected), sex=sex, applicant_address=address,
                has_business_license=has_license, trade_license_number=trade_license_no or None, trade=trade or None,
                registration_number=reg_no or None, tin_number=tin_no or None, date_of_business_license=str(date_of_license) if (has_license and date_of_license) else None,
                enterprise_category=ent_cat, ownership_form=owner_form, business_sector=sector,
                number_of_owners=int(owners_n), owners_names=owners_names, registered_address=reg_addr,
                business_premise=premise, male_employees=int(male_emp), female_employees=int(female_emp),
                business_capital_etb=float(capital), monthly_revenue_etb=float(monthly_rev),
                annual_revenue_last3=float(annual_rev3), net_profit_last3=float(net_profit),
                financing_required_etb=float(finance_req), source_of_repayment=repay_src, purpose_of_funds=fund_purpose,
                guarantor_first_name=g_fn, guarantor_father_name=g_fan, guarantor_grandfather_name=g_gfn,
                guarantor_phone=g_phone, guarantor_monthly_income=float(g_income),
                credit_history=credit_hist, cbe_account_number=cbe_acc, cbe_branch=cbe_branch, cbe_city=cbe_city, mode_of_finance=mode_fin,
                collected_by=st.session_state.user["id"]
            )
            # Save to cloud/local
            if supabase:
                res = supabase.table("applicants").insert(rec).execute()
                if res.data:
                    st.success("Saved to cloud")
                else:
                    st.error("Cloud save failed")
            else:
                save_jsonl("data/applicants.jsonl", rec)
                st.success("Saved locally (demo mode)")

def admin_page():
    st.subheader("Admin Dashboard")
    if not is_admin(st.session_state.user["email"]):
        st.error("Admins only")
        return

    # Load all applicants
    if supabase_admin:
        res = supabase_admin.table("applicants").select("*").order("auto_number").execute()
        rows = res.data or []
    elif supabase:
        res = supabase.table("applicants").select("*").execute()
        rows = res.data or []
    else:
        rows = load_jsonl("data/applicants.jsonl")

    df = pd.DataFrame(rows)
    st.dataframe(df)

    # Edit selected row (admin only)
    if not df.empty:
        st.markdown("### Edit Selected Applicant")
        idx = st.number_input("Row index", min_value=0, max_value=len(df)-1, step=1, value=0)
        row = df.iloc[int(idx)].to_dict()
        # Simple example: update credit_history
        new_credit = st.text_input("Credit History", value=row.get("credit_history",""))
        if st.button("Update Credit History"):
            if supabase_admin:
                supabase_admin.table("applicants").update({"credit_history": new_credit}).eq("id", row["id"]).execute()
            else:
                # local update
                rows[int(idx)]["credit_history"] = new_credit
                # rewrite file
                with open("data/applicants.jsonl","w") as f:
                    for r in rows:
                        f.write(json.dumps(r)+"\n")
            st.success("Updated")

    # Export Excel (Sheets 1–3)
    if st.button("Download Excel (Sheets 1–3)"):
        df = pd.DataFrame(rows)
        # Fill auto_number if not available (local mode fallback)
        if "auto_number" not in df.columns:
            df["auto_number"] = range(1, len(df)+1)
        out_path = "EDI_export.xlsx"
        export_excel(df, out_path)
        with open(out_path, "rb") as f:
            st.download_button("Download file", data=f.read(), file_name="EDI_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- Route ----
if role == "admin":
    admin_page()
else:
    collector_page()
