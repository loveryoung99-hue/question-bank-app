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

# ================= الثوابت المحدثة والمراحل المحددة فقط =================
STAGES_LIST = [
    "السادس العلمي", 
    "السادس الأدبي", 
    "الثالث المتوسط", 
    "السادس الابتدائي"
]

TERMS_LIST = ["الدور الأول", "الدور الثاني", "الدور الثالث"]

SHARED_SUBJECTS = ["اللغة العربية", "اللغة الإنجليزية", "الاسلامية"]
SCIENTIFIC_SUBJECTS = ["الرياضيات", "الفيزياء", "الكيمياء", "الأحياء"]
LITERARY_SUBJECTS = ["التاريخ", "الجغرافيا", "الرياضيات", "الاقتصاد"]
GENERAL_SUBJECTS = ["الرياضيات", "اللغة العربية", "اللغة الإنجليزية", "الاسلامية", "الاجتماعيات", "العلوم"]

def get_subjects_for_stage(stage):
    if "العلمي" in str(stage):
        return sorted(SCIENTIFIC_SUBJECTS + SHARED_SUBJECTS)
    elif "الأدبي" in str(stage):
        return sorted(LITERARY_SUBJECTS + SHARED_SUBJECTS)
    elif "الثالث" in str(stage):
        return sorted(GENERAL_SUBJECTS)
    elif "السادس الابتدائي" in str(stage) or "الابتدائي" in str(stage):
        return sorted(GENERAL_SUBJECTS)
    else:
        return sorted(GENERAL_SUBJECTS + SCIENTIFIC_SUBJECTS + LITERARY_SUBJECTS)

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
    أنت خبير في تحليل الأوراق الامتحانية العراقية للمراحل التالية: (السادس العلمي، السادس الأدبي، الثالث المتوسط، السادس الابتدائي). 
    قم بتحليل الصور المرفقة حسب ترتيبها الدقيق واستخراج البيانات التالية بصيغة JSON حصرية بدون أي نصوص أخرى:
    {
      "subject": "اسم المادة (مثل: الرياضيات، الفيزياء، الكيمياء، الأحياء، اللغة العربية، اللغة الإنجليزية، الاسلامية، التاريخ، الجغرافيا، الاقتصاد، الاجتماعيات، العلوم)",
      "year": "السنة الدراسية (مثال: 2024)",
      "stage": "المرحلة (اختر من: السادس العلمي، السادس الأدبي، الثالث المتوسط، السادس الابتدائي)",
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
                model='gemini-3.6-flash',
                contents=contents
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
            
        except Exception as e:
            continue

    st.error("❌ فشلت محاولات الاتصال عبر مفاتيح الـ API المتاحة.")
    return None

# ================= 4. الشريط الجانبي (Sidebar) لمتابعة حالة المواد =================
with st.sidebar:
    st.header("📊 حالة المواد المرفوعة")
    st.markdown("متابعة فورية لكافة المواد المرفوعة.")
    
    cloud_exams_status_check = fetch_cloud_exams()
    uploaded_keys = set()
    for ex in cloud_exams_status_check:
        stg_val = ex.get('stage') or "أخرى"
        sbj_val = ex.get('subject') or "عام"
        trm_val = ex.get('term') or "الدور الأول"
        uploaded_keys.add(f"{stg_val}_{sbj_val}_{trm_val}")

    for stg in STAGES_LIST:
        with st.expander(f"📌 {stg}", expanded=False):
            subs = get_subjects_for_stage(stg)
            stage_table_data = []
            for sbj in subs:
                for trm in TERMS_LIST:
                    key_str = f"{stg}_{sbj}_{trm}"
                    # التحقق المرن أيضا في الشريط الجانبي
                    is_uploaded = any(key_str in uk or (stg in uk and sbj in uk) for uk in uploaded_keys)
                    if is_uploaded:
                        stage_table_data.append({
                            "المادة": sbj,
                            "الدور": trm,
                            "الحالة": "🟢 مرفوع"
                        })
            if not stage_table_data:
                st.info("لا توجد مواد مرفوعة مسجلة بدقة لهذه المرحلة.")
            else:
                st.dataframe(stage_table_data, use_container_width=True, hide_index=True)

# ================= 5. الواجهة الرئيسية والتنقل =================
st.title("📚 بنك الأسئلة الامتحانية - منصة 99+1")

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
    
    if pdf_file is not None:
        try:
            pdf_reader = pypdf.PdfReader(pdf_file)
            st.info(f"تم رفع ملف PDF بنجاح يحتوي على {len(pdf_reader.pages)} صفحة.")
        except Exception as e:
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

        if st.button("🔍 استخراج وتحليل الأسئلة عبر الذكاء الاصطناعي", type="primary"):
            with st.spinner("جاري قراءة الصفحات وتحليل الأسئلة بدقة..."):
                extracted = extract_exam_data_via_gemini(images_to_process)
                if extracted:
                    st.success("تم التحليل بنجاح! طابق الحقول بالأسفل.")
                    st.session_state['extracted_data'] = extracted

    data = st.session_state.get('extracted_data', {})
    
    st.markdown("---")
    st.subheader("⚙️ تحديد تصنيف الورقة الامتحانية:")
    
    col_in1, col_in2, col_in3, col_in4 = st.columns(4)
    
    with col_in1:
        ai_stage = data.get("stage", "السادس العلمي")
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
        ai_term = data.get("term", "الدور الأول")
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
            "term": selected_term,
            "branch": "عام",
            "questions_data": editable_questions
        }
        insert_cloud_exam(final_record)

# ----------------- التبويب الثاني: العرض الهيكلي للمجلدات (تم جعل العرض مرناً وشاملاً للقديم والجديد) -----------------
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
            stg = exam.get("stage") or "أخرى غير مصنفة"
            
            # تصنيف مرن للمراحل لضمان عدم ضياع أي سجل قديم
            matched_stage = "أخرى غير مصنفة"
            for known_stg in STAGES_LIST:
                if known_stg in str(stg):
                    matched_stage = known_stg
                    break
            if matched_stage == "أخرى غير مصنفة" and stg in STAGES_LIST:
                matched_stage = stg

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
                                                curr_stg = exam.get("stage", STAGES_LIST[0])
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
                                                        "term": e_term,
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
