import streamlit as st
import requests
import json
from PIL import Image, ImageEnhance
from google import genai
from google.genai import types
import streamlit.components.v1 as components
import pypdf
import io

# ================= 1. الإعدادات والصفحة =================
st.set_page_config(
    page_title="بنك الأسئلة الامتحانية",
    page_icon="📚",
    layout="wide"
)

# ================= تصميم عملي ومحسّن مع الحفاظ على كامل الوظائف =================
st.markdown(
    """
    <style>
        :root {
            --app-bg: #f6f8fc;
            --surface: #ffffff;
            --text-main: #162238;
            --text-muted: #667085;
            --border: #e4e8f0;
            --primary: #173b69;
            --primary-soft: #edf3fb;
            --accent: #d99328;
        }

        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
            direction: rtl;
        }

        .stApp {
            background: var(--app-bg);
            color: var(--text-main);
        }

        .block-container {
            max-width: 1480px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3, h4, h5, h6, p, label, div {
            text-align: right;
        }

        [data-testid="stSidebar"] {
            background: var(--surface);
            border-left: 1px solid var(--border);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.2rem;
        }

        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.55rem;
            background: var(--surface);
            padding: 0.45rem;
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(26, 44, 73, 0.05);
        }

        div[data-testid="stTabs"] button[data-baseweb="tab"] {
            flex: 1;
            min-height: 48px;
            border-radius: 12px;
            font-weight: 700;
            color: var(--text-muted);
        }

        div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
            background: var(--primary-soft);
            color: var(--primary);
        }

        div[data-testid="stFileUploader"] section {
            background: var(--surface);
            border: 1.5px dashed #b9c7da;
            border-radius: 16px;
            padding: 0.6rem;
        }

        div[data-baseweb="select"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            border-radius: 11px !important;
            border-color: var(--border) !important;
            background: var(--surface) !important;
        }

        [data-testid="stExpander"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: 0.55rem;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 11px;
            min-height: 42px;
            font-weight: 700;
            border: 1px solid var(--border);
        }

        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {
            background: var(--primary);
            color: #ffffff;
            border-color: var(--primary);
        }

        [data-testid="stAlert"] {
            border-radius: 12px;
        }

        hr {
            border-color: var(--border);
            margin: 1.35rem 0;
        }

        @media (max-width: 800px) {
            .block-container {
                padding-left: 0.75rem;
                padding-right: 0.75rem;
            }
            div[data-testid="stTabs"] button[data-baseweb="tab"] {
                font-size: 0.82rem;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# جلب المفاتيح بأمان تام من Streamlit Secrets
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
GEMINI_KEYS = st.secrets.get("GEMINI_KEYS", [])

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def clean_supabase_url(url):
    url = url.rstrip('/')
    if url.endswith('/rest/v1'):
        url = url[:-8]
    return url.rstrip('/')

# ================= الثوابت والمراحل المحددة فقط =================
STAGES_LIST = [
    "السادس الإعدادي",
    "الثالث المتوسط",
    "السادس الابتدائي"
]

TERMS_LIST = ["الدور الأول", "الدور الثاني", "الدور الثالث"]

SHARED_SUBJECTS = ["اللغة العربية", "اللغة الإنجليزية", "الاسلامية"]
SCIENTIFIC_SUBJECTS = ["الرياضيات", "الفيزياء", "الكيمياء", "الأحياء"]
LITERARY_SUBJECTS = ["التاريخ", "الجغرافيا", "الرياضيات", "الاقتصاد"]
GENERAL_SUBJECTS = ["الرياضيات", "اللغة العربية", "اللغة الإنجليزية", "الاسلامية", "الاجتماعيات", "العلوم"]
PREPARATORY_SUBJECTS = sorted(set(SCIENTIFIC_SUBJECTS + LITERARY_SUBJECTS + SHARED_SUBJECTS))

def normalize_stage(stage):
    stage_text = str(stage or "").strip()

    # دمج التسميات القديمة (العلمي/الأدبي) تحت السادس الإعدادي دون حذف البيانات القديمة.
    if any(label in stage_text for label in [
        "السادس العلمي", "السادس الأدبي", "السادس الإعدادي",
        "السادس الاعدادي", "السادس اعدادي"
    ]):
        return "السادس الإعدادي"

    if "الثالث" in stage_text and "المتوسط" in stage_text:
        return "الثالث المتوسط"

    if "السادس" in stage_text and ("الابتدائي" in stage_text or "ابتدائي" in stage_text):
        return "السادس الابتدائي"

    return None

def get_subjects_for_stage(stage):
    normalized_stage = normalize_stage(stage) or str(stage)
    if normalized_stage == "السادس الإعدادي":
        return PREPARATORY_SUBJECTS
    elif normalized_stage == "الثالث المتوسط":
        return sorted(GENERAL_SUBJECTS)
    elif normalized_stage == "السادس الابتدائي":
        return sorted(GENERAL_SUBJECTS)
    else:
        return sorted(GENERAL_SUBJECTS)

YEARS_LIST = [str(y) for y in range(2026, 2010, -1)]

# ================= دالة التحسين الضمني للصور =================
def enhance_image_silently(img):
    try:
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(1.4)
        sharpness_enhancer = ImageEnhance.Sharpness(img_enhanced)
        img_final = sharpness_enhancer.enhance(1.5)
        return img_final
    except Exception:
        return img

# ================= 2. دوال التعامل مع Supabase =================
def fetch_cloud_exams():
    if not SUPABASE_URL:
        return []
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?select=*"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"خطأ جلب البيانات (رمز {res.status_code}): {res.text}")
            return []
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")
        return []

def insert_cloud_exam(exam_record):
    if not SUPABASE_URL or not exam_record:
        st.error("رابط Supabase مفقود أو البيانات فارغة.")
        return
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        table_name = "exam_papers"
        
        url = f"{base_url}/rest/v1/{table_name}"
        res = requests.post(url, headers=HEADERS, json=exam_record)
        
        if res.status_code in [200, 201]:
            st.success("✅ تم حفظ الورقة الامتحانية بنجاح!")
            if 'extracted_data' in st.session_state:
                del st.session_state['extracted_data']
            st.rerun()
        else:
            st.error(f"❌ خطأ في الحفظ (رمز الحالة {res.status_code}):")
            st.code(res.text)
    except Exception as e:
        st.error(f"خطأ استثنائي في الاتصال بالسحاب: {e}")

def update_cloud_exam(exam_id, updated_record):
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.patch(url, headers=HEADERS, json=updated_record)
        if res.status_code in [200, 204]:
            st.success("✅ تم تحديث التعديلات بنجاح!")
            st.rerun()
        else:
            st.error(f"خطأ في التحديث ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

def delete_cloud_exam(exam_id):
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.delete(url, headers=HEADERS)
        if res.status_code in [200, 204]:
            st.warning("🗑️ تم حذف الورقة الامتحانية!")
            st.rerun()
        else:
            st.error(f"خطأ في الحذف ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

# ================= 3. دالة الاستخراج الذكي عبر Gemini =================
def extract_exam_data_via_gemini(images_list):
    if not GEMINI_KEYS:
        st.error("يرجى إعداد قائمة GEMINI_KEYS بشكل صحيح في إعدادات Secrets الخاصة بـ Streamlit!")
        return None

    prompt = """
    أنت خبير في تحليل الأوراق الامتحانية العراقية للمراحل التالية حصراً: (السادس الإعدادي، الثالث المتوسط، السادس الابتدائي). 
    قم بتحليل ملف PDF أو الصور المرفقة حسب ترتيبها الدقيق واستخراج البيانات التالية بصيغة JSON حصرية بدون أي نصوص أخرى:
    {
      "subject": "اسم المادة (مثل: الرياضيات، الفيزياء، الكيمياء، الأحياء، اللغة العربية، اللغة الإنجليزية، الاسلامية، التاريخ، الجغرافيا، الاقتصاد، الاجتماعيات، العلوم)",
      "year": "السنة الدراسية (مثال: 2024)",
      "stage": "المرحلة (اختر حصراً من: السادس الإعدادي، الثالث المتوسط، السادس الابتدائي)",
      "term": "الدور (اختر بدقة: الدور الأول أو الدور الثاني أو الدور الثالث، وإذا لم يذكر ضع: الدور الأول)",
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
    contents = [prompt] + images_list

    for idx, api_key in enumerate(GEMINI_KEYS):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
            
        except Exception as e:
            continue

    st.error("❌ فشلت محاولات الاتصال عبر مفاتيح الـ API المتاحة.")
    return None

# ================= 4. الشريط الجانبي (Sidebar) لمتابعة حالة الرفع =================
with st.sidebar:
    st.header("📊 متابعة الرفع")
    st.markdown("اعرف بسرعة شنو مرفوع وشنو باقي حسب المرحلة والسنة والدور.")

    cloud_exams_status_check = fetch_cloud_exams()

    # المفتاح الآن يشمل السنة حتى تكون حالة الرفع دقيقة لكل سنة ودور.
    uploaded_keys = set()
    for ex in cloud_exams_status_check:
        stg_val = normalize_stage(ex.get('stage'))
        if not stg_val:
            continue
        sbj_val = ex.get('subject') or "عام"
        yr_val = str(ex.get('year') or "").strip()
        trm_val = ex.get('term') or "الدور الأول"
        if yr_val:
            uploaded_keys.add((stg_val, sbj_val, yr_val, trm_val))

    # فلاتر المتابعة
    filter_stage = st.selectbox(
        "المرحلة",
        STAGES_LIST,
        key="status_filter_stage"
    )

    filter_year = st.selectbox(
        "السنة",
        YEARS_LIST,
        key="status_filter_year"
    )

    available_subjects = get_subjects_for_stage(filter_stage)
    filter_subject = st.selectbox(
        "المادة",
        ["الكل"] + available_subjects,
        key="status_filter_subject"
    )

    filter_term = st.selectbox(
        "الدور",
        ["الكل"] + TERMS_LIST,
        key="status_filter_term"
    )

    filter_status = st.selectbox(
        "الحالة",
        ["الكل", "🔴 باقي", "🟢 مرفوع"],
        key="status_filter_status"
    )

    sort_mode = st.selectbox(
        "الترتيب",
        ["الباقي أولاً", "المرفوع أولاً", "حسب المادة", "حسب الدور"],
        key="status_sort_mode"
    )

    # حساب تقدم الرفع للمرحلة والسنة المحددتين بالكامل، قبل تطبيق فلاتر المادة/الدور/الحالة.
    full_status_rows = []
    for sbj in available_subjects:
        for trm in TERMS_LIST:
            is_uploaded = (filter_stage, sbj, filter_year, trm) in uploaded_keys
            full_status_rows.append({
                "المادة": sbj,
                "السنة": filter_year,
                "الدور": trm,
                "الحالة": "🟢 مرفوع" if is_uploaded else "🔴 باقي"
            })

    total_items = len(full_status_rows)
    uploaded_count = sum(1 for row in full_status_rows if row["الحالة"] == "🟢 مرفوع")
    remaining_count = total_items - uploaded_count
    progress_value = (uploaded_count / total_items) if total_items else 0.0

    st.markdown("---")
    st.markdown(f"**التقدم — {filter_stage} / {filter_year}**")
    st.progress(progress_value)

    m1, m2 = st.columns(2)
    with m1:
        st.metric("مرفوع", uploaded_count)
    with m2:
        st.metric("باقي", remaining_count)

    # تطبيق الفلاتر على الجدول المرئي.
    stage_table_data = []
    for row in full_status_rows:
        if filter_subject != "الكل" and row["المادة"] != filter_subject:
            continue
        if filter_term != "الكل" and row["الدور"] != filter_term:
            continue
        if filter_status != "الكل" and row["الحالة"] != filter_status:
            continue
        stage_table_data.append(row)

    # ترتيب عملي لمعرفة النواقص أولاً أو حسب رغبة المستخدم.
    term_order = {term: idx for idx, term in enumerate(TERMS_LIST)}
    status_order_remaining_first = {"🔴 باقي": 0, "🟢 مرفوع": 1}
    status_order_uploaded_first = {"🟢 مرفوع": 0, "🔴 باقي": 1}

    if sort_mode == "الباقي أولاً":
        stage_table_data.sort(key=lambda row: (
            status_order_remaining_first.get(row["الحالة"], 9),
            row["المادة"],
            term_order.get(row["الدور"], 9)
        ))
    elif sort_mode == "المرفوع أولاً":
        stage_table_data.sort(key=lambda row: (
            status_order_uploaded_first.get(row["الحالة"], 9),
            row["المادة"],
            term_order.get(row["الدور"], 9)
        ))
    elif sort_mode == "حسب الدور":
        stage_table_data.sort(key=lambda row: (
            term_order.get(row["الدور"], 9),
            row["المادة"]
        ))
    else:
        stage_table_data.sort(key=lambda row: (
            row["المادة"],
            term_order.get(row["الدور"], 9)
        ))

    st.markdown("---")
    if not stage_table_data:
        st.info("لا توجد نتائج مطابقة للفلاتر الحالية.")
    else:
        st.dataframe(
            stage_table_data,
            use_container_width=True,
            hide_index=True,
            height=min(560, 38 + (len(stage_table_data) * 35))
        )

# ================= 5. الواجهة الرئيسية والتنقل =================
st.markdown(
    """
    <div style="background:#ffffff;border:1px solid #e4e8f0;border-radius:18px;padding:20px 22px;margin-bottom:16px;box-shadow:0 10px 28px rgba(26,44,73,.05);">
        <div style="font-size:1.55rem;font-weight:800;color:#173b69;">📚 بنك الأسئلة الامتحانية — منصة 99+1</div>
        <div style="margin-top:6px;color:#667085;font-size:.95rem;">رفع وتحليل ومراجعة وإدارة الأوراق الامتحانية من واجهة واحدة.</div>
    </div>
    """,
    unsafe_allow_html=True
)

tab1, tab2, tab3 = st.tabs([
    "📤 رفع وتحليل ورقة امتحانية", 
    "📁 إدارة الأوراق الامتحانية (المجلدات)",
    "📥 تصدير واستيراد البيانات (Backup)"
])

# ----------------- التبويب الأول: الرفع والتحليل -----------------
with tab1:
    st.subheader("رفع مستند PDF أو تحديد الصور بدقة (الأولى والثانية)")
    
    pdf_file = st.file_uploader("📄 (اختياري) رفع ملف PDF للأسئلة", type=["pdf"])
    
    st.markdown("---")
    st.markdown("### أو رفع الصور بشكل منفصل لضمان الترتيب التام:")
    col_img1, col_img2 = st.columns(2)
    
    with col_img1:
        st.markdown("#### 🖼️ الصورة الأولى (الصفحة الأولى)")
        img_file_1 = st.file_uploader("اختر صورة الصفحة الأولى", type=["jpg", "jpeg", "png"], key="img_1")
        
    with col_img2:
        st.markdown("#### 🖼️ الصورة الثانية (الصفحة الثانية - إن وجدت)")
        img_file_2 = st.file_uploader("اختر صورة الصفحة الثانية", type=["jpg", "jpeg", "png"], key="img_2")
    
    images_to_process = []
    pdf_part = None
    
    if pdf_file is not None:
        try:
            pdf_bytes = pdf_file.getvalue()
            pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pdf_part = types.Part.from_bytes(
                data=pdf_bytes,
                mime_type="application/pdf"
            )
            st.success(f"✅ تم تجهيز ملف PDF للتحليل ويحتوي على {len(pdf_reader.pages)} صفحة.")
        except Exception as e:
            pdf_part = None
            st.error(f"قراءة ملف الـ PDF فشلت: {e}")

    if img_file_1:
        pil_1 = Image.open(img_file_1)
        enhanced_1 = enhance_image_silently(pil_1)
        images_to_process.append(enhanced_1)
        
    if img_file_2:
        pil_2 = Image.open(img_file_2)
        enhanced_2 = enhance_image_silently(pil_2)
        images_to_process.append(enhanced_2)

    if images_to_process:
        st.markdown("---")
        st.markdown("### 👀 معاينة الصور المرفوعة:")
        cols = st.columns(len(images_to_process))
        for idx, img_p in enumerate(images_to_process):
            with cols[idx]:
                st.image(img_p, caption=f"الصفحة #{idx+1} (محسنة)", use_container_width=True)

    has_analysis_input = (pdf_part is not None) or bool(images_to_process)
    if has_analysis_input:
        analysis_inputs = []
        if pdf_part is not None:
            analysis_inputs.append(pdf_part)
        analysis_inputs.extend(images_to_process)

        if st.button("🔍 استخراج وتحليل الأسئلة عبر الذكاء الاصطناعي", type="primary"):
            with st.spinner("جاري قراءة الصفحات وتحليل الأسئلة بدقة..."):
                extracted = extract_exam_data_via_gemini(analysis_inputs)
                if extracted:
                    st.success("تم التحليل بنجاح! طابق الحقول بالأسفل.")
                    st.session_state['extracted_data'] = extracted

    data = st.session_state.get('extracted_data', {})
    
    st.markdown("---")
    st.subheader("⚙️ تحديد تصنيف الورقة الامتحانية:")
    
    col_in1, col_in2, col_in3, col_in4 = st.columns(4)
    
    with col_in1:
        ai_stage = data.get("stage", STAGES_LIST[0])
        default_stage_idx = 0
        for i, s in enumerate(STAGES_LIST):
            if s in str(ai_stage):
                default_stage_idx = i
                break
        selected_stage = st.selectbox("المرحلة", STAGES_LIST, index=default_stage_idx)
        
    with col_in2:
        current_stage_subjects = get_subjects_for_stage(selected_stage)
        ai_subject = data.get("subject", current_stage_subjects[0])
        default_sub_idx = 0
        for i, sub in enumerate(current_stage_subjects):
            if sub in str(ai_subject):
                default_sub_idx = i
                break
        selected_subject = st.selectbox("المادة", current_stage_subjects, index=default_sub_idx)
        
    with col_in3:
        ai_year = str(data.get("year", "2024"))
        default_yr_idx = YEARS_LIST.index(ai_year) if ai_year in YEARS_LIST else 0
        selected_year = st.selectbox("السنة", YEARS_LIST, index=default_yr_idx)

    with col_in4:
        ai_term = data.get("term", TERMS_LIST[0])
        default_term_idx = 0
        for i, t in enumerate(TERMS_LIST):
            if t in str(ai_term):
                default_term_idx = i
                break
        selected_term = st.selectbox("الدور", TERMS_LIST, index=default_term_idx)

    st.markdown("---")
    st.subheader("📋 الأسئلة المستخرجة والمراجعة:")
    
    q_list = data.get("questions", [])
    editable_questions = []

    for idx, q in enumerate(q_list):
        st.markdown(f"**السؤال / الفرع #{idx+1}**")
        c_q1, c_q2 = st.columns([1, 1])
        with c_q1:
            q_num = st.text_input("رقم السؤال", value=q.get("question_number", ""), key=f"gen_qnum_{idx}")
        with c_q2:
            q_mark = st.text_input("الدرجة", value=q.get("mark", ""), key=f"gen_qmark_{idx}")
        
        q_cnt = st.text_area("نص السؤال", value=q.get("content", ""), height=90, key=f"gen_qcnt_{idx}")
        q_svg = st.text_area("كود SVG للرسم", value=q.get("svg_code", ""), height=70, key=f"gen_qsvg_{idx}")
        
        if q_svg.strip():
            st.markdown("🎨 **معاينة الرسم الهندسي:**")
            components.html(f"<div style='display: flex; justify-content: center; background: white; padding: 10px; border-radius: 5px;'>{q_svg}</div>", height=150, scrolling=True)
        
        editable_questions.append({
            "question_number": q_num,
            "mark": q_mark,
            "content": q_cnt,
            "svg_code": q_svg
        })
        st.markdown("---")

    if st.button("💾 حفظ النموذج النهائي في قاعدة البيانات السحابية", type="primary"):
        final_record = {
            "subject": selected_subject,
            "year": selected_year,
            "stage": selected_stage,
            "term": selected_term,  # عامود مستقل للدور
            "branch": "عام",
            "questions_data": editable_questions
        }
        insert_cloud_exam(final_record)

# ----------------- التبويب الثاني: العرض الهيكلي للمجلدات (مع تطابق مرن للملفات السابقة والجديدة) -----------------
with tab2:
    st.subheader("📁 الأوراق الامتحانية (عرض الهيكلية والمجلدات)")
    
    col_r1, col_r2 = st.columns([1, 4])
    with col_r1:
        if st.button("🔄 تحديث القائمة"):
            st.rerun()

    cloud_exams = fetch_cloud_exams()

    if not cloud_exams:
        st.info("لا توجد أوراق امتحانية مخزنة حتى الآن في قاعدة البيانات.")
    else:
        tree = {}
        for exam in cloud_exams:
            matched_stage = normalize_stage(exam.get("stage"))

            # إظهار المراحل الثلاث المطلوبة فقط. السجلات القديمة للسادس العلمي/الأدبي تندمج تحت السادس الإعدادي.
            if not matched_stage:
                continue

            sbj = exam.get("subject") or "عام"
            yr  = str(exam.get("year") or "بدون سنة")
            trm = exam.get("term") or "الدور الأول"

            tree.setdefault(matched_stage, {})\
                .setdefault(sbj, {})\
                .setdefault(yr, {})\
                .setdefault(trm, []).append(exam)

        for stg_name, subjects in tree.items():
            with st.expander(f"🎓 مجلد المرحلة: **{stg_name}**", expanded=True):
                for sbj_name, years in subjects.items():
                    with st.expander(f"📚 المادة: **{sbj_name}**", expanded=False):
                        for yr_name, terms in years.items():
                            with st.expander(f"📅 سنة: **{yr_name}**", expanded=False):
                                for trm_name, exams_list in terms.items():
                                    for exam in exams_list:
                                        exam_id = exam.get("id")
                                        
                                        with st.expander(f"📌 **{trm_name}** (انقر للتعديل أو العرض)", expanded=True):
                                            st.markdown("#### ✏️ تعديل بيانات الورقة:")
                                            
                                            c1, c2, c3, c4 = st.columns(4)
                                            with c1:
                                                curr_stg = normalize_stage(exam.get("stage")) or STAGES_LIST[0]
                                                idx_stg = STAGES_LIST.index(curr_stg) if curr_stg in STAGES_LIST else 0
                                                e_stage = st.selectbox("المرحلة", STAGES_LIST, index=idx_stg, key=f"stg_{exam_id}")
                                            with c2:
                                                valid_subs = get_subjects_for_stage(e_stage)
                                                curr_sub = exam.get("subject", valid_subs[0])
                                                idx_sub = valid_subs.index(curr_sub) if curr_sub in valid_subs else 0
                                                e_subject = st.selectbox("المادة", valid_subs, index=idx_sub, key=f"sub_{exam_id}")
                                            with c3:
                                                curr_yr = str(exam.get("year", YEARS_LIST[0]))
                                                idx_yr = YEARS_LIST.index(curr_yr) if curr_yr in YEARS_LIST else 0
                                                e_year = st.selectbox("السنة", YEARS_LIST, index=idx_yr, key=f"yr_{exam_id}")
                                            with c4:
                                                curr_trm = exam.get("term", TERMS_LIST[0])
                                                idx_trm = TERMS_LIST.index(curr_trm) if curr_trm in TERMS_LIST else 0
                                                e_term = st.selectbox("الدور", TERMS_LIST, index=idx_trm, key=f"trm_{exam_id}")

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
                                                
                                                if q_svg.strip():
                                                    st.markdown("🎨 **معاينة الرسم الهندسي:**")
                                                    components.html(f"<div style='display: flex; justify-content: center; background: white; padding: 10px; border-radius: 5px;'>{q_svg}</div>", height=150, scrolling=True)
                                                
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
                                                        "stage": e_stage,
                                                        "term": e_term, # تحديث الدور في العامود المستقل
                                                        "branch": "عام",
                                                        "questions_data": updated_q_list
                                                    }
                                                    update_cloud_exam(exam_id, updated_record)
                                            
                                            with btn_c2:
                                                if st.button("🗑️ حذف الورقة بالكامل", key=f"del_{exam_id}"):
                                                    delete_cloud_exam(exam_id)

# ----------------- التبويب الثالث: تصدير واستيراد البيانات -----------------
with tab3:
    st.subheader("📥 تصدير واستيراد قاعدة البيانات بالكامل (Backup)")
    st.markdown("من هنا يمكنك حفظ نسخة احتياطية من كافة الأسئلة والمجلدات والتقسيمات بملف واحد بصيغة JSON، أو استعادة نسخة سابقة.")

    col_exp, col_imp = st.columns(2)

    with col_exp:
        st.markdown("### 📤 تصدير البيانات (Export)")
        st.info("اضغط على الزر أدناه لتنزيل ملف يحتوي على كل الأسئلة والتقسيمات المخزنة حالياً في قاعدة البيانات.")
        
        all_exams_data = fetch_cloud_exams()
        if all_exams_data:
            json_string = json.dumps(all_exams_data, ensure_ascii=False, indent=4)
            st.download_button(
                label="📥 تحميل ملف النسخة الاحتياطية (JSON)",
                data=json_string,
                file_name="99_plus_1_exams_backup.json",
                mime="application/json",
                type="primary"
            )
        else:
            st.warning("لا توجد بيانات كافية للتصدير حالياً.")

    with col_imp:
        st.markdown("### 📥 استيراد البيانات (Import)")
        st.warning("⚠️ ملاحظة: عند رفع ملف النسخة الاحتياطية، سيتم إدخال البيانات المضمنة فيه إلى قاعدة البيانات الحالية.")
        
        uploaded_backup_file = st.file_uploader("اختر ملف النسخة الاحتياطية (.json)", type=["json"])
        
        if uploaded_backup_file is not None:
            if st.button("🚀 بدء رفع واستعادة البيانات إلى قاعدة البيانات", type="primary"):
                try:
                    backup_content = json.load(uploaded_backup_file)
                    if isinstance(backup_content, list):
                        base_url = clean_supabase_url(SUPABASE_URL)
                        url = f"{base_url}/rest/v1/exam_papers"
                        
                        success_count = 0
                        for record in backup_content:
                            if 'id' in record:
                                del record['id']
                            
                            res = requests.post(url, headers=HEADERS, json=record)
                            if res.status_code in [200, 201]:
                                success_count += 1
                                
                        st.success(f"✅ تمت استعادة بنجاح ({success_count}) ورقة امتحانية إلى قاعدة البيانات!")
                        st.rerun()
                    else:
                        st.error("❌ صيغة الملف غير صحيحة، يجب أن يكون ملف JSON يمثل قائمة من الأوراق الامتحانية.")
                except Exception as e:
                    st.error(f"خطأ أثناء قراءة أو استيراد الملف: {e}")
