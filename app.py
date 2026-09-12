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
    page_title="منصة 99+1 - بنك الأسئلة الامتحانية",
    page_icon="📚",
    layout="wide"
)

# جلب المفاتيح بأمان تام من Streamlit Secrets
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
# جلب قائمة المفاتيح بدلاً من مفتاح واحد
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

# ================= الثوابت المحدثة =================
STAGES_LIST = ["السادس الاعدادي", "الخامس الاعدادي", "الرابع الاعدادي"]
BRANCHES_LIST = ["العلمي", "الأدبي", "المواد المشتركة"]

SHARED_SUBJECTS = ["اللغة العربية", "اللغة الإنجليزية", "الاسلامية"]
SCIENTIFIC_SUBJECTS = ["الرياضيات", "الفيزياء", "الكيمياء", "الأحياء"]
LITERARY_SUBJECTS = ["التاريخ", "الجغرافيا", "الرياضيات", "الاقتصاد"]

YEARS_LIST = [str(y) for y in range(2026, 2010, -1)]
TERMS_LIST = ["الدور الأول", "الدور الثاني", "الدور الثالث", "تمهيدي"]

def get_subjects_for_branch(branch):
    if branch == "العلمي":
        return sorted(SCIENTIFIC_SUBJECTS)
    elif branch == "الأدبي":
        return sorted(LITERARY_SUBJECTS)
    else:
        return sorted(SHARED_SUBJECTS)

# ================= دالة التحسين الضمني للصور =================
def enhance_image_silently(img):
    """تقوم بتحسين التباين والجودة تلقائياً بشكل ضمني قبل إرسالها لـ Gemini"""
    try:
        # تحسين التباين بمقدار 1.4
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(1.4)
        
        # تحسين الحدة (Sharpness) لضمان وضوح النصوص
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
            st.warning("🗑️ تم حذف الورقة الامتحانية!")
            st.rerun()
        else:
            st.error(f"خطأ في الحذف ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

# ================= 3. دالة الاستخراج الذكي عبر Gemini مع التدوير التلقائي =================
def extract_exam_data_via_gemini(images_list):
    if not GEMINI_KEYS:
        st.error("يرجى إعداد قائمة GEMINI_KEYS بشكل صحيح في إعدادات Secrets الخاصة بـ Streamlit!")
        return None

    prompt = """
    أنت خبير في تحليل الأوراق الامتحانية العراقية للمراحل (السادس، الخامس، والرابع الإعدادي). 
    قم بتحليل الصور المرفقة حسب ترتيبها الدقيق (الصورة الأولى ثم الصورة الثانية إن وجدت) واستخراج البيانات التالية بصيغة JSON حصرية بدون أي نصوص أخرى:
    {
      "subject": "اسم المادة (مثل: الرياضيات، الفيزياء، الكيمياء، الأحياء، اللغة العربية، اللغة الإنجليزية، الاسلامية، التاريخ، الجغرافيا، الاقتصاد)",
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

    # المرور على المفاتيح بالتسلسل
    for idx, api_key in enumerate(GEMINI_KEYS):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-1.5-flash', # تم تصحيح اسم الموديل للأحدث والأسرع
                contents=contents
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
            
        except Exception as e:
            err_str = str(e)
            # إذا كان الخطأ بسبب تجاوز الحد (429) أو استنفاد الحصة، انتقل للمفتاح التالي مباشرة
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                continue
            else:
                # إذا كان خطأ غير متوقع، نعرض تحذيراً ونستمر بتجربة باقي المفاتيح
                st.warning(f"ملاحظة (المفتاح {idx+1}): {e}")
                continue

    # إذا انتهت الحلقة ولم تنجح أي محاولة
    st.error("❌ لقد استنفدت حصة جميع مفاتيح الـ API المتاحة لليوم أو حدث خطأ يمنع الاتصال. يرجى المحاولة لاحقاً.")
    return None

# ================= 4. الواجهة الرئيسية والتنقل =================
st.title("📚 بنك الأسئلة الامتحانية - منصة 99+1")

tab1, tab2 = st.tabs(["📤 رفع وتحليل ورقة امتحانية", "📁 إدارة الأوراق الامتحانية (المجلدات)"])

# ----------------- التبويب الأول: الرفع والتحليل -----------------
with tab1:
    st.subheader("رفع مستند PDF أو تحديد الصور بدقة (الأولى والثانية)")
    
    # خيار رفع ملف PDF كامل
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
    
    # معالجة ملف الـ PDF إذا تم رفعه وتحويل صفحاته إلى صور
    if pdf_file is not None:
        try:
            pdf_reader = pypdf.PdfReader(pdf_file)
            st.info(f"تم رفع ملف PDF بنجاح يحتوي على {len(pdf_reader.pages)} صفحة.")
        except Exception as e:
            st.error(f"قراءة ملف الـ PDF فشلت: {e}")

    # تجميع الصور حسب الترتيب الصحيح لمنع أي تقديم أو تأخير
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
        st.markdown("### 👀 معاينة الصور المرفوعة (مع التحسين الضمني للوضوح والتباين):")
        cols = st.columns(len(images_to_process))
        for idx, img_p in enumerate(images_to_process):
            with cols[idx]:
                st.image(img_p, caption=f"الصفحة #{idx+1} (محسنة)", use_container_width=True)

        if st.button("🔍 استخراج وتحليل الأسئلة عبر الذكاء الاصطناعي", type="primary"):
            with st.spinner("جاري قراءة الصفحات وتحليل الأسئلة بدقة... (قد يستغرق بضع ثوانٍ)"):
                extracted = extract_exam_data_via_gemini(images_to_process)
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
