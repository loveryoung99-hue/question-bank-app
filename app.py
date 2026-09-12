import streamlit as st
import requests
import json
from PIL import Image, ImageEnhance
from google import genai
from google.genai import types
from streamlit_cropper import st_cropper
import streamlit.components.v1 as components

# ================= 1. الإعدادات والصفحة =================
st.set_page_config(
    page_title="منصة 99+1 - بنك الأسئلة الامتحانية",
    page_icon="📚",
    layout="wide"
)

# جلب المفاتيح بأمان تام من Streamlit Secrets
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

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

# ================= الثوابت المحدثة =================
STAGES_LIST = ["السادس الاعدادي", "الخامس الاعدادي", "الرابع الاعدادي"]
BRANCHES_LIST = ["العلمي", "الأدبي", "المواد المشتركة"]

SHARED_SUBJECTS = ["اللغة العربية", "اللغة الإنجليزية", "الاسلامية"]
SCIENTIFIC_SUBJECTS = ["الرياضيات", "الفيزياء", "الكيمياء", "الأحياء"]
LITERARY_SUBJECTS = ["التاريخ", "الجغرافيا", "الرياضيات", " الاقتصاد"]

YEARS_LIST = [str(y) for y in range(2026, 2010, -1)]
TERMS_LIST = ["الدور الأول", "الدور الثاني", "الدور الثالث", "تمهيدي"]

def get_subjects_for_branch(branch):
    if branch == "العلمي":
        return sorted(SCIENTIFIC_SUBJECTS)
    elif branch == "الأدبي":
        return sorted(LITERARY_SUBJECTS)
    else:
        return sorted(SHARED_SUBJECTS)

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
        
        check_url = f"{base_url}/rest/v1/{table_name}?subject=eq.{exam_record['subject']}&year=eq.{exam_record['year']}&term=eq.{exam_record['term']}&stage=eq.{exam_record['stage']}&branch=eq.{exam_record['branch']}"
        check_res = requests.get(check_url, headers=HEADERS)
        
        if check_res.status_code == 200 and len(check_res.json()) > 0:
            st.warning("⚠️ هذه الورقة الامتحانية مخزنة مسبقاً في قاعدة البيانات لنفس التصنيف!")
            return

        url = f"{base_url}/rest/v1/{table_name}"
        res = requests.post(url, headers=HEADERS, json=exam_record)
        
        if res.status_code in [200, 201]:
            st.success("✅ تم حفظ الورقة الامتحانية بنجاح!")
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
            st.success("🗑️ تم حذف الورقة الامتحانية!")
            st.rerun()
        else:
            st.error(f"خطأ في الحذف ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

# ================= 3. دالة الاستخراج الذكي عبر Gemini (تدعم صور متعددة) =================
def extract_exam_data_via_gemini(images_list):
    if not GEMINI_API_KEY:
        st.error("يرجى إعداد GEMINI_API_KEY في إعدادات Secrets الخاصة بـ Streamlit!")
        return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = """
        أنت خبير في تحليل الأوراق الامتحانية العراقية للمراحل (السادس، الخامس، والرابع الإعدادي). 
        قم بتحليل الصور المرفقة (سواء كانت صفحة واحدة أو عدة صفحات لنفس الامتحان) واستخراج البيانات التالية بصيغة JSON حصرية بدون أي نصوص أخرى:
        {
          "subject": "اسم المادة (مثل: الرياضيات، الفيزياء، الكيمياء، الأحياء، اللغة العربية، اللغة الإنجليزية، الاسلامية، التاريخ، الجغرافيا)",
          "year": "السنة الدراسية (مثال: 2024)",
          "term": "الدور (مثال: الدور الأول أو الدور الثاني أو الدور الثالث أو تمهيدي)",
          "stage": "المرحلة (اختر حصراً من: السادس الاعدادي، الخامس الاعدادي، الرابع الاعدادي)",
          "branch": "الفرع أو القسم (اختر: العلمي أو الأدبي أو المواد المشتركة بناءً على المادة المستخرجة)",
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
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=contents
        )
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"فشل في استخراج البيانات عبر AI: {e}")
        return None

# ================= 4. الواجهة الرئيسية والتنقل =================
st.title("📚 بنك الأسئلة الامتحانية - منصة 99+1")

tab1, tab2 = st.tabs(["📤 رفع وتحليل ورقة امتحانية", "📁 إدارة الأوراق الامتحانية (المجلدات)"])

# ----------------- التبويب الأول: الرفع والقص والتحسين -----------------
with tab1:
    st.subheader("تحليل ورقة/أوراق امتحانية واختيار التصنيفات")
    
    # السماح برفع ملفات متعددة (صور صفحات الأسئلة)
    uploaded_files = st.file_uploader("اختر صورة أو عدة صور للأسئلة الامتحانية", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        st.markdown("---")
        st.markdown("### ✂️ قص وتحسين الأجزاء المطلوبة لكل صفحة:")
        
        processed_crops = []
        
        # حقن CSS لمنع تجاوز الحواف في الشاشات الصغيرة للموبايل
        st.markdown(
            """
            <style>
            .stCropperContainer {
                max-width: 100% !important;
                overflow-x: auto !important;
            }
            textarea {
                direction: auto !important;
                text-align: start !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        for i, up_file in enumerate(uploaded_files):
            raw_img = Image.open(up_file)
            
            with st.expander(f"📱 خيارات العرض والقص للصفحة #{i+1}", expanded=True):
                resize_factor = st.slider(f"تصغير عرض الصفحة #{i+1} (لحل مشكلة حواف الموبايل)", 0.3, 1.0, 0.8, 0.05, key=f"scale_{i}")
                
                if resize_factor < 1.0:
                    new_w = int(raw_img.width * resize_factor)
                    new_h = int(raw_img.height * resize_factor)
                    display_img = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                else:
                    display_img = raw_img

            col_crop_view, col_result_view = st.columns(2)
            
            with col_crop_view:
                st.info(f"حدد الجزء المطلوب من الصفحة #{i+1}:")
                cropped_img = st_cropper(
                    display_img, 
                    realtime_update=True, 
                    box_color='#FF0000', 
                    aspect_ratio=None, 
                    key=f"cropper_tool_{i}",
                    box_style="outline",
                    return_type='image'
                )
                
            with col_result_view:
                st.info(f"📌 معاينة وتعديل الصفحة #{i+1}:")
                if cropped_img is not None:
                    processed_crop = cropped_img.copy()
                    
                    with st.expander(f"🛠️ تباين وتدوير للصفحة #{i+1}", expanded=False):
                        c_rot, c_enh = st.columns(2)
                        with c_rot:
                            crop_rotation = st.selectbox("تدوير", [0, 90, 180, 270], format_func=lambda x: f"{x}°", key=f"crop_rot_{i}")
                            if crop_rotation != 0:
                                processed_crop = processed_crop.rotate(crop_rotation, expand=True)
                        with c_enh:
                            crop_contrast = st.slider("مستوى التباين", 0.5, 3.0, 1.0, 0.1, key=f"crop_contrast_{i}")
                            if crop_contrast != 1.0:
                                enhancer = ImageEnhance.Contrast(processed_crop)
                                processed_crop = enhancer.enhance(crop_contrast)
                    
                    st.image(processed_crop, caption=f"معاينة الجزء المقصوص للصفحة #{i+1}", use_container_width=True)
                    processed_crops.append(processed_crop)
            
            st.markdown("---")

        if processed_crops and st.button("🔍 استخراج البيانات بالذكاء الاصطناعي لجميع الصفحات", type="primary"):
            with st.spinner("جاري تحليل الصفحات والأسئلة واستخراج المحتوى..."):
                extracted = extract_exam_data_via_gemini(processed_crops)
                if extracted:
                    st.success("تم التحليل بنجاح! طابق الحقول بالأسفل.")
                    st.session_state['extracted_data'] = extracted

    data = st.session_state.get('extracted_data', {})
    
    st.markdown("---")
    st.subheader("⚙️ تحديد تصنيف الورقة الامتحانية:")
    
    col_in1, col_in2, col_in3, col_in4, col_in5 = st.columns(5)
    
    with col_in1:
        ai_stage = data.get("stage", "السادس الاعدادي")
        default_stage_idx = STAGES_LIST.index(ai_stage) if ai_stage in STAGES_LIST else 0
        selected_stage = st.selectbox("المرحلة", STAGES_LIST, index=default_stage_idx)
        
    with col_in2:
        ai_branch = data.get("branch", "العلمي")
        if "المشتركة" in ai_branch or "مشتركة" in ai_branch:
            ai_branch = "المواد المشتركة"
        elif "الأدبي" in ai_branch:
            ai_branch = "الأدبي"
        elif "العلمي" in ai_branch:
            ai_branch = "العلمي"
            
        default_branch_idx = BRANCHES_LIST.index(ai_branch) if ai_branch in BRANCHES_LIST else 0
        selected_branch = st.selectbox("الفرع / القسم", BRANCHES_LIST, index=default_branch_idx)
        
    with col_in3:
        current_branch_subjects = get_subjects_for_branch(selected_branch)
        ai_subject = data.get("subject", "الرياضيات")
        default_sub_idx = current_branch_subjects.index(ai_subject) if ai_subject in current_branch_subjects else 0
        selected_subject = st.selectbox("المادة", current_branch_subjects, index=default_sub_idx)
        
    with col_in4:
        ai_year = str(data.get("year", "2024"))
        default_yr_idx = YEARS_LIST.index(ai_year) if ai_year in YEARS_LIST else 0
        selected_year = st.selectbox("السنة", YEARS_LIST, index=default_yr_idx)
        
    with col_in5:
        ai_term = data.get("term", "الدور الأول")
        default_term_idx = TERMS_LIST.index(ai_term) if ai_term in TERMS_LIST else 0
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
            st.markdown("🎨 **معاينة الرسم الهندسي (مطابق للأصل):**")
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
            "term": selected_term,
            "stage": selected_stage,
            "branch": selected_branch,
            "questions_data": editable_questions
        }
        insert_cloud_exam(final_record)

# ----------------- التبويب الثاني: العرض الهيكلي للمجلدات -----------------
with tab2:
    st.subheader("📁 الأوراق الامتحانية (عرض الهيكلية والمجلدات)")
    
    if st.button("🔄 تحديث القائمة"):
        st.rerun()

    cloud_exams = fetch_cloud_exams()

    if not cloud_exams:
        st.info("لا توجد أوراق امتحانية مخزنة حتى الآن.")
    else:
        tree = {}
        for exam in cloud_exams:
            stg = exam.get("stage") or "غير محدد"
            brn = exam.get("branch") or "العلمي"
            sbj = exam.get("subject") or "غير محدد"
            yr  = str(exam.get("year") or "غير محدد")
            trm = exam.get("term") or "غير محدد"

            tree.setdefault(stg, {})\
                .setdefault(brn, {})\
                .setdefault(sbj, {})\
                .setdefault(yr, {})\
                .setdefault(trm, []).append(exam)

        for stg_name, branches in tree.items():
            with st.expander(f"🎓 مجلد المرحلة: **{stg_name}**", expanded=False):
                for brn_name, subjects in branches.items():
                    with st.expander(f"📂 الفرع / القسم: **{brn_name}**", expanded=False):
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
                                                        e_stage = st.selectbox("المرحلة", STAGES_LIST, index=STAGES_LIST.index(exam.get("stage")) if exam.get("stage") in STAGES_LIST else 0, key=f"stg_{exam_id}")
                                                    with c2:
                                                        current_brn = exam.get("branch")
                                                        if current_brn not in BRANCHES_LIST:
                                                            current_brn = "العلمي"
                                                        e_branch = st.selectbox("الفرع", BRANCHES_LIST, index=BRANCHES_LIST.index(current_brn), key=f"brn_{exam_id}")
                                                    with c3:
                                                        valid_subs = get_subjects_for_branch(e_branch)
                                                        current_sub = exam.get("subject")
                                                        if current_sub not in valid_subs:
                                                            current_sub = valid_subs[0]
                                                        e_subject = st.selectbox("المادة", valid_subs, index=valid_subs.index(current_sub), key=f"sub_{exam_id}")
                                                    with c4:
                                                        e_year = st.selectbox("السنة", YEARS_LIST, index=YEARS_LIST.index(str(exam.get("year"))) if str(exam.get("year")) in YEARS_LIST else 0, key=f"yr_{exam_id}")
                                                    with c5:
                                                        e_term = st.selectbox("الدور", TERMS_LIST, index=TERMS_LIST.index(exam.get("term")) if exam.get("term") in TERMS_LIST else 0, key=f"tm_{exam_id}")

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
                                                            st.markdown("🎨 **معاينة الرسم الهندسي (مطابق للأصل):**")
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
                                                                "term": e_term,
                                                                "stage": e_stage,
                                                                "branch": e_branch,
                                                                "questions_data": updated_q_list
                                                            }
                                                            update_cloud_exam(exam_id, updated_record)
                                                    
                                                    with btn_c2:
                                                        if st.button("🗑️ حذف الورقة بالكامل", key=f"del_{exam_id}"):
                                                            delete_cloud_exam(exam_id)
