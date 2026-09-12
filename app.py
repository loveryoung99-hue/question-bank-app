import streamlit as st
import requests
import json
from PIL import Image
from google import genai
from google.genai import types
from streamlit_cropper import st_cropper

# ================= 1. الإعدادات والصفحة =================
st.set_page_config(
    page_title="منصة 99+1 - بنك الأسئلة الامتحانية",
    page_icon="📚",
    layout="wide"
)

# جلب المفاتيح من Streamlit Secrets أو البيئة
SUPABASE_URL = "https://wtmkotentkrqvirvquzn.supabase.co/rest/v1/"  
SUPABASE_KEY = "sb_publishable_NtDev7qGyAaw0vCNxjRR2w_VoIrmZlG"
client = genai.Client(api_key="AQ.Ab8RN6KzvpJLTiGzt8K-6kqelmu0OTz7pPvcuL-BoslZlX2UFg")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def clean_supabase_url(url):
    return url.rstrip('/')

# ================= 2. دوال التعامل مع Supabase =================
def fetch_cloud_exams():
    if not SUPABASE_URL or "ضع_" in SUPABASE_URL:
        return []
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?select=*"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json()
        return []
    except Exception as e:
        st.error(f"خطأ في جلب البيانات: {e}")
        return []

def insert_cloud_exam(exam_record):
    if not SUPABASE_URL or "ضع_" in SUPABASE_URL or not exam_record:
        return
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        
        # فحص لمنع تكرار نفس النموذج المرفوع مسبقاً
        check_url = f"{base_url}/rest/v1/exam_papers?subject=eq.{exam_record['subject']}&year=eq.{exam_record['year']}&term=eq.{exam_record['term']}&stage=eq.{exam_record['stage']}&branch=eq.{exam_record['branch']}"
        check_res = requests.get(check_url, headers=HEADERS)
        
        if check_res.status_code == 200 and len(check_res.json()) > 0:
            st.warning("⚠️ هذه الورقة الامتحانية مخزنة مسبقاً في قاعدة البيانات!")
            return

        url = f"{base_url}/rest/v1/exam_papers"
        res = requests.post(url, headers=HEADERS, json=exam_record)
        if res.status_code in [200, 201]:
            st.success("✅ تم حفظ الورقة الامتحانية بنجاح!")
            st.rerun()
        else:
            st.error(f"خطأ في الحفظ: {res.text}")
    except Exception as e:
        st.error(f"خطأ الاتصال بالسحاب: {e}")

def update_cloud_exam(exam_id, updated_record):
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.patch(url, headers=HEADERS, json=updated_record)
        if res.status_code in [200, 204]:
            st.success("✅ تم تحديث التعديلات بنجاح!")
            st.rerun()
        else:
            st.error(f"خطأ في التحديث: {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

def delete_cloud_exam(exam_id):
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.delete(url, headers=HEADERS)
        if res.status_code in [200, 204]:
            st.success("🗑️ تم حذف الورقة الامتحانية!")
            st.rerun()
        else:
            st.error(f"خطأ في الحذف: {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

# ================= 3. دالة الاستخراج الذكي عبر Gemini =================
def extract_exam_data_via_gemini(image):
    if not GEMINI_API_KEY:
        st.error("يرجى إدخال GEMINI_API_KEY في إعدادات Secrets!")
        return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = """
        أنت خبير في تحليل الأوراق الامتحانية العراقية. قم بتحليل الصورة واستخراج البيانات التالية بصيغة JSON حصرية بدون أي نصوص أخرى:
        {
          "subject": "اسم المادة",
          "year": "السنة الدراسية (مثال: 2024)",
          "term": "الدور (مثال: الدور الأول)",
          "stage": "المرحلة (مثال: السادس الاعدادي)",
          "branch": "الفرع (مثال: العلمي أو الأدبي)",
          "questions": [
             {
               "question_number": "رقم السؤال/الفرع (مثال: س1/أ)",
               "content": "نص السؤال كاملاً",
               "mark": "الدرجة إن وجدت",
               "svg_code": "أي رسم هندسي أو توضيحي تحوله لكود SVG إن وجد، وإلا اتركه فارغاً"
             }
          ]
        }
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image]
        )
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"فشل في استخراج البيانات عبر AI: {e}")
        return None

# ================= 4. الواجهة الرئيسية والتنقل =================
st.title("📚 بنك الأسئلة الامتحانية - منصة 99+1")

tab1, tab2 = st.tabs(["📤 رفع وتحليل ورقة امتحانية", "📁 إدارة الأوراق الامتحانية (المجلدات)"])

# ----------------- التبويب الأول: الرفع والقص -----------------
with tab1:
    st.subheader("تحليل ورقة امتحانية من صورة")
    uploaded_file = st.file_uploader("اختر صورة الورقة الامتحانية", type=["jpg", "jpeg", "png"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.info("💡 يمكنك قص الجزء المطلوب من الصورة لزيادة دقة التحليل:")
        cropped_img = st_cropper(img, realtime_update=True, box_color='#FF0000', aspect_ratio=None)
        
        if st.button("🔍 استخراج البيانات وحفظها تلقائياً", type="primary"):
            with st.spinner("جاري تحليل الأسئلة واستخراج المحتوى..."):
                extracted = extract_exam_data_via_gemini(cropped_img)
                if extracted:
                    st.success("تم التحليل بنجاح!")
                    
                    exam_record = {
                        "subject": extracted.get("subject", "غير محدد"),
                        "year": str(extracted.get("year", "2024")),
                        "term": extracted.get("term", "الدور الأول"),
                        "stage": extracted.get("stage", "السادس الاعدادي"),
                        "branch": extracted.get("branch", "العلمي"),
                        "questions_data": extracted.get("questions", [])
                    }
                    insert_cloud_exam(exam_record)

# ----------------- التبويب الثاني: العرض الهيكلي للمجلدات -----------------
with tab2:
    st.subheader("📁 الأوراق الامتحانية (عرض الهيكلية والمجلدات)")
    
    if st.button("🔄 تحديث البيانات"):
        st.rerun()

    cloud_exams = fetch_cloud_exams()

    if not cloud_exams:
        st.info("لا توجد أوراق امتحانية مخزنة حتى الآن.")
    else:
        # بناء الهيكل الشجري للمجلدات
        tree = {}
        for exam in cloud_exams:
            stg = exam.get("stage") or "غير محدد"
            brn = exam.get("branch") or "عام"
            sbj = exam.get("subject") or "غير محدد"
            yr  = str(exam.get("year") or "غير محدد")
            trm = exam.get("term") or "غير محدد"

            tree.setdefault(stg, {})\
                .setdefault(brn, {})\
                .setdefault(sbj, {})\
                .setdefault(yr, {})\
                .setdefault(trm, []).append(exam)

        # عرض المجلدات المتداخلة
        for stg_name, branches in tree.items():
            with st.expander(f"🎓 مجلد المرحلة: **{stg_name}**", expanded=False):
                for brn_name, subjects in branches.items():
                    with st.expander(f"📂 الفرع: **{brn_name}**", expanded=False):
                        for sbj_name, years in subjects.items():
                            with st.expander(f"📚 المادة: **{sbj_name}**", expanded=False):
                                for yr_name, terms in years.items():
                                    with st.expander(f"📅 سنة: **{yr_name}**", expanded=False):
                                        for trm_name, exams_list in terms.items():
                                            for exam in exams_list:
                                                exam_id = exam.get("id")
                                                
                                                with st.expander(f"📝 **{trm_name}** (انقر للتعديل أو العرض)", expanded=False):
                                                    st.markdown("#### ✏️ تعديل بيانات الورقة:")
                                                    
                                                    c1, c2, c3, c4, c5 = st.columns(5)
                                                    with c1:
                                                        e_subject = st.text_input("المادة", value=exam.get("subject", ""), key=f"sub_{exam_id}")
                                                    with c2:
                                                        e_year = st.text_input("السنة", value=exam.get("year", ""), key=f"yr_{exam_id}")
                                                    with c3:
                                                        e_term = st.text_input("الدور", value=exam.get("term", ""), key=f"tm_{exam_id}")
                                                    with c4:
                                                        e_stage = st.text_input("المرحلة", value=exam.get("stage", ""), key=f"stg_{exam_id}")
                                                    with c5:
                                                        e_branch = st.text_input("الفرع", value=exam.get("branch", ""), key=f"brn_{exam_id}")

                                                    st.markdown("---")
                                                    st.markdown("### 📋 الأسئلة والمحتوى:")
                                                    
                                                    q_list = exam.get("questions_data", [])
                                                    updated_q_list = []

                                                    for idx, q in enumerate(q_list):
                                                        st.markdown(f"**السؤال / الفرع #{idx+1}**")
                                                        col_q1, col_q2 = st.columns([1, 1])
                                                        with col_q1:
                                                            q_num = st.text_input("رقم السؤال", value=q.get("question_number", ""), key=f"qnum_{exam_id}_{idx}")
                                                        with col_q2:
                                                            q_mark = st.text_input("الدرجة", value=q.get("mark", ""), key=f"qmark_{exam_id}_{idx}")
                                                        
                                                        q_cnt = st.text_area("نص السؤال", value=q.get("content", ""), height=90, key=f"qcnt_{exam_id}_{idx}")
                                                        q_svg = st.text_area("كود SVG للرسم", value=q.get("svg_code", ""), height=70, key=f"qsvg_{exam_id}_{idx}")
                                                        
                                                        updated_q_list.append({
                                                            "question_number": q_num,
                                                            "mark": q_mark,
                                                            "content": q_cnt,
                                                            "svg_code": q_svg
                                                        })
                                                        st.markdown("---")

                                                    btn_c1, btn_c2 = st.columns([1, 1])
                                                    with btn_c1:
                                                        if st.button("💾 حفظ التعديلات", key=f"save_{exam_id}"):
                                                            updated_record = {
                                                                "subject": e_subject,
                                                                "year": e_year,
                                                                "term": e_term,
                                                                "stage": e_stage,
                                                                "branch": e_branch,
                                                                "questions_data": updated_q_list
                                                            }
                                                            update_cloud_exam(exam_id, updated_record)
                                                    
                                                    with btn_c2:
                                                        if st.button("🗑️ حذف الورقة بالكامل", key=f"del_{exam_id}"):
                                                            delete_cloud_exam(exam_id)
