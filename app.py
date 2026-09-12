import json
import re
import io
import pandas as pd
import requests
from PIL import Image, ImageEnhance, ImageOps
import streamlit as st
from streamlit_cropper import st_cropper
from google import genai
from google.genai import types

st.set_page_config(layout="wide", page_title="بنك الأسئلة السحابي الموحد")
st.title("🌐 بنك الأسئلة السحابي المشترك (أوراق امتحانية كاملة)")

# --- ضع المفاتيح المباشرة هنا ---
SUPABASE_URL = "https://wtmkotentkrqvirvquzn.supabase.co/rest/v1/"  
SUPABASE_KEY = "sb_publishable_NtDev7qGyAaw0vCNxjRR2w_VoIrmZlG"
GEMINI_API_KEY = "AQ.Ab8RN6LWMZaofavEmyWG8h16yx1fHkecKW-IEapQriduO_ybBQ"  

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- تنظيف رابط Supabase ---
def clean_supabase_url(url: str) -> str:
    clean_url = url.strip()
    if clean_url.endswith("/rest/v1/"):
        clean_url = clean_url[:-9]
    elif clean_url.endswith("/rest/v1"):
        clean_url = clean_url[:-8]
    return clean_url.rstrip('/')

# --- دوال التعامل مع السحاب (جدول exam_papers) ---
def fetch_cloud_exams():
    if "ضع_" in SUPABASE_URL:
        return []
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?select=*&order=id.asc"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"خطأ في جلب البيانات: {res.text}")
            return []
    except Exception as e:
        st.error(f"خطأ الاتصال بالسحاب: {e}")
        return []

def insert_cloud_exam(exam_record):
    if "ضع_" in SUPABASE_URL or not exam_record:
        return
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers"
        res = requests.post(url, headers=HEADERS, json=exam_record)
        if res.status_code in [200, 201]:
            st.success("تم حفظ النسخة الامتحانية بالكامل في سجل واحد بنجاح!")
        else:
            st.error(f"خطأ في الحفظ: {res.text}")
    except Exception as e:
        st.error(f"خطأ الاتصال بالسحاب: {e}")

def update_cloud_exam(exam_id, updated_record):
    if "ضع_" in SUPABASE_URL:
        return
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.patch(url, headers=HEADERS, json=updated_record)
        if res.status_code in [200, 204]:
            st.success("تم تحديث بيانات الورقة الامتحانية على السحاب بنجاح!")
            st.rerun()
        else:
            st.error(f"خطأ في التعديل: {res.text}")
    except Exception as e:
        st.error(f"خطأ الاتصال بالسحاب: {e}")

def delete_cloud_exam(exam_id):
    if "ضع_" in SUPABASE_URL:
        return
    try:
        base_url = clean_supabase_url(SUPABASE_URL)
        url = f"{base_url}/rest/v1/exam_papers?id=eq.{exam_id}"
        res = requests.delete(url, headers=HEADERS)
        if res.status_code in [200, 204]:
            st.success("تم حذف الورقة الامتحانية بنجاح!")
            st.rerun()
        else:
            st.error(f"خطأ في الحذف: {res.text}")
    except Exception as e:
        st.error(f"خطأ الاتصال بالسحاب: {e}")

# --- معالجة JSON مع رموز LaTeX ---
def clean_and_parse_json(json_str: str):
    cleaned = re.sub(r"^```json\s*", "", json_str.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE).strip()
    cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', cleaned)

    try:
        return json.loads(cleaned)
    except Exception:
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            fixed_str = cleaned.replace('\\', '\\\\')
            return json.loads(fixed_str, strict=False)

# --- دالة معالجة وتحسين الصورة (تاثير CamScanner) ---
def apply_camscanner_filter(img: Image.Image, filter_type: str, brightness: float, contrast: float) -> Image.Image:
    processed = img.convert("RGB")
    
    # تطبيق الفلتر المطلوبة
    if filter_type == "أسود وأبيض (CamScanner Document)":
        processed = ImageOps.grayscale(processed)
        # زيادة التباين لتنقية الخلفية البيضاء والنص الأسود
        enhancer_c = ImageEnhance.Contrast(processed)
        processed = enhancer_c.enhance(2.0 * contrast)
        enhancer_b = ImageEnhance.Brightness(processed)
        processed = enhancer_b.enhance(1.2 * brightness)
        processed = processed.convert("RGB")
    elif filter_type == "توضيح الألوان (Magic Color)":
        enhancer_c = ImageEnhance.Contrast(processed)
        processed = enhancer_c.enhance(1.4 * contrast)
        enhancer_s = ImageEnhance.Color(processed)
        processed = enhancer_s.enhance(1.3)
        enhancer_b = ImageEnhance.Brightness(processed)
        processed = enhancer_b.enhance(brightness)
    else: # رمادي ناعم
        processed = ImageOps.grayscale(processed).convert("RGB")
        enhancer_c = ImageEnhance.Contrast(processed)
        processed = enhancer_c.enhance(contrast)
        enhancer_b = ImageEnhance.Brightness(processed)
        processed = enhancer_b.enhance(brightness)
        
    return processed

# --- الشريط الجانبي ---
st.sidebar.header("⚙️ الإعدادات والبيانات")
model_name = st.sidebar.text_input("اسم النموذج", value="gemini-3.6-flash")

st.sidebar.markdown("---")
st.sidebar.subheader("📋 بيانات الامتحان الحالية")

stage = st.sidebar.selectbox("المرحلة الدراسية", ["السادس الاعدادي", "الثالث المتوسط", "الرابع العلمي", "الخامس العلمي", "أخرى"])
branch = "عام"
if stage == "السادس الاعدادي":
    branch = st.sidebar.selectbox("الفرع", ["العلمي", "الأدبي", "مشترك (علمي + أدبي)"])

subjects_list = [
    "الفيزياء",
    "الكيمياء",
    "الأحياء",
    "الرياضيات",
    "اللغة العربية",
    "اللغة الإنجليزية",
    "التربية الإسلامية",
    "مادة أخرى..."
]

selected_subject = st.sidebar.selectbox("المادة الدراسية", subjects_list)
subject = st.sidebar.text_input("اكتب اسم المادة يدويًا", value="") if selected_subject == "مادة أخرى..." else selected_subject

exam_year = st.sidebar.text_input("السنة الدراسية", value="2024")
exam_term = st.sidebar.selectbox("الدور", ["الدور الأول", "الدور الثاني", "الدور الثالث", "التمهيدي", "خاص/خارجي"])

tab1, tab2 = st.tabs(["📤 رفع ومعالجة ورقة امتحانية", "🔍 البنك السحابي (عرض وتعديل)"])

# ================= التبويب الأول (تحديد الإطار والمعالجة) =================
with tab1:
    if "ضع_" in SUPABASE_URL or "ضع_" in GEMINI_API_KEY:
        st.warning("⚠️ يرجى تعبئة مفاتيح Supabase و Gemini API الكاملة في بداية الملف.")

    upload_mode = st.radio(
        "اختر طريقة إدخال الصورة:",
        ["🖼️ اختيار من الاستوديو / الملفات", "📷 التقاط من الكاميرا مباشرة"],
        horizontal=True
    )

    col_up1, col_up2 = st.columns([3, 1])
    raw_uploaded_file = None

    with col_up1:
        if upload_mode == "🖼️ اختيار من الاستوديو / الملفات":
            raw_uploaded_file = st.file_uploader("اختر صورة الأسئلة", type=["jpg", "png", "jpeg"])
        else:
            raw_uploaded_file = st.camera_input("التقط صورة لورقة الأسئلة")

    with col_up2:
        st.write(" ")
        st.write(" ")
        if st.button("🔄 مسح/إعادة الضبط"):
            if "current_file" in st.session_state:
                del st.session_state["current_file"]
            if "extracted_questions" in st.session_state:
                del st.session_state["extracted_questions"]
            st.rerun()

    if raw_uploaded_file:
        file_identifier = getattr(raw_uploaded_file, "name", "camera_capture.jpg")
        raw_image = Image.open(raw_uploaded_file)

        st.markdown("---")
        st.subheader("✂️ 1. تحديد إطار الورقة وتحسين الوضوح (CamScanner)")

        col_crop, col_controls = st.columns([2, 1])

        with col_controls:
            st.markdown("##### 🎛️ إعدادات المعالجة والفلتر:")
            filter_option = st.selectbox(
                "نمط الفلتر",
                ["أسود وأبيض (CamScanner Document)", "توضيح الألوان (Magic Color)", "تدرج الرمادي الناعم"]
            )
            brightness_val = st.slider("السطوع (Brightness)", 0.5, 2.0, 1.0, 0.1)
            contrast_val = st.slider("التباين (Contrast)", 0.5, 2.5, 1.0, 0.1)
            box_color = st.color_picker("لون إطار التحديد", "#00FF00")

        with col_crop:
            st.caption("👈 قم بسحب وإعادة تحجيم الإطار لتحديد ورقة الأسئلة بدقة:")
            # مكون تحديد إطار الصورة وتقطيعها
            cropped_image = st_cropper(
                raw_image,
                realtime_update=True,
                box_color=box_color,
                aspect_ratio=None,
                key="doc_cropper"
            )

        # تطبيق التحسينات على الجزء المقتطع
        final_processed_image = apply_camscanner_filter(cropped_image, filter_option, brightness_val, contrast_val)

        st.markdown("---")
        st.subheader("🖼️ المعاينة النهائية والتحليل عبر الذكاء الاصطناعي")
        
        col_preview, col_extracted = st.columns([1, 1])
        
        with col_preview:
            st.image(final_processed_image, caption="الورقة المعالجة الجاهزة للإرسال", use_container_width=True)
            analyze_btn = st.button("⚡ بدء استخراج الأسئلة من الورقة المعالجة", type="primary", use_container_width=True)

        if analyze_btn and "ضع_" not in GEMINI_API_KEY and "ضع_" not in SUPABASE_URL:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)

                # تحويل الصورة المعالجة إلى bytes
                img_byte_arr = io.BytesIO()
                final_processed_image.save(img_byte_arr, format="JPEG")
                image_bytes = img_byte_arr.getvalue()

                with st.spinner("جاري استخراج كافة أسئلة الورقة وفروعها..."):
                    prompt = """
                    استخرج جميع الأسئلة والفروع الموجودة في هذه الصورة.
                    1. إعادة رسم أي شكل توضيحي بكود SVG احترافي ونظيف في حقل "svg_code".
                    2. ضع علامات التنصيص المفردة (') فقط داخل كود الـ SVG.
                    3. ضع نص السؤال فقط في حقل "content".
                    4. عند كتابة معادلات LaTeX، استخدم (\\\\) بدلاً من (\\).

                    JSON Format:
                    [
                       {
                          "question_number": "رقم السؤال/الفرع",
                          "mark": "الدرجة",
                          "content": "نص السؤال",
                          "svg_code": "<svg>...</svg>"
                       }
                    ]
                    """

                    response = client.models.generate_content(
                        model=model_name.strip(),
                        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt],
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    )

                    raw_data = clean_and_parse_json(response.text)
                    st.session_state.extracted_questions = raw_data if isinstance(raw_data, list) else [raw_data]
                    st.session_state.current_file = file_identifier

            except Exception as e:
                st.error(f"حدث خطأ أثناء المعالجة: {e}")

        questions = st.session_state.get("extracted_questions", [])

        with col_extracted:
            if questions:
                st.subheader(f"الأسئلة المستخرجة ({len(questions)} فرع/سؤال)")
                edited_questions = []
                
                for idx, q in enumerate(questions):
                    with st.expander(f"📌 {q.get('question_number', f'سؤال {idx+1}')}", expanded=False):
                        q_num = st.text_input(f"رقم السؤال #{idx+1}", value=q.get("question_number", ""), key=f"num_{idx}")
                        q_mark = st.text_input(f"الدرجة #{idx+1}", value=q.get("mark", ""), key=f"mark_{idx}")
                        q_content = st.text_area(f"نص السؤال #{idx+1}", value=q.get("content", ""), height=100, key=f"content_{idx}")
                        q_svg = st.text_area(f"كود الـ SVG #{idx+1}", value=q.get("svg_code", ""), height=80, key=f"svg_{idx}")

                        edited_questions.append({
                            "question_number": q_num,
                            "mark": q_mark,
                            "content": q_content,
                            "svg_code": q_svg
                        })

                if st.button("☁️ حفظ الورقة الامتحانية كاملة في سجل واحد", use_container_width=True):
                    full_exam_record = {
                        "image_name": file_identifier,
                        "stage": stage,
                        "branch": branch,
                        "subject": subject,
                        "year": exam_year,
                        "term": exam_term,
                        "questions_data": edited_questions
                    }
                    insert_cloud_exam(full_exam_record)

# ================= التبويب الثاني =================
with tab2:
    st.subheader("🌐 الأوراق الامتحانية المخزنة (إدارة وتعديل أوراق كاملة)")
    
    if st.button("🔄 تحديث البيانات"):
        st.rerun()

    cloud_exams = fetch_cloud_exams()

    if cloud_exams:
        for exam in cloud_exams:
            exam_id = exam.get("id")
            exam_title = f"📄 {exam.get('subject')} - {exam.get('year')} {exam.get('term')} | {exam.get('stage')} ({exam.get('branch')})"
            
            with st.expander(exam_title, expanded=False):
                st.markdown("#### ✏️ تعديل بيانات الورقة والأسئلة:")
                
                c_head1, c_head2, c_head3, c_head4 = st.columns(4)
                with c_head1:
                    e_subject = st.text_input("المادة", value=exam.get("subject", ""), key=f"ex_sub_{exam_id}")
                with c_head2:
                    e_year = st.text_input("السنة", value=exam.get("year", ""), key=f"ex_yr_{exam_id}")
                with c_head3:
                    e_term = st.text_input("الدور", value=exam.get("term", ""), key=f"ex_tm_{exam_id}")
                with c_head4:
                    e_stage = st.text_input("المرحلة", value=exam.get("stage", ""), key=f"ex_stg_{exam_id}")

                st.markdown("---")
                st.markdown("### 📋 أسئلة وفروع الورقة الامتحانية:")
                
                q_list = exam.get("questions_data", [])
                updated_q_list = []

                for idx, q in enumerate(q_list):
                    st.markdown(f"**الفرع/السؤال #{idx+1}**")
                    col_q1, col_q2 = st.columns([1, 1])
                    with col_q1:
                        q_num = st.text_input("رقم السؤال / الفرع", value=q.get("question_number", ""), key=f"eq_num_{exam_id}_{idx}")
                    with col_q2:
                        q_mark = st.text_input("الدرجة", value=q.get("mark", ""), key=f"eq_mark_{exam_id}_{idx}")
                    
                    q_cnt = st.text_area("نص السؤال", value=q.get("content", ""), height=90, key=f"eq_cnt_{exam_id}_{idx}")
                    q_svg = st.text_area("كود SVG (المخطط)", value=q.get("svg_code", ""), height=70, key=f"eq_svg_{exam_id}_{idx}")
                    
                    updated_q_list.append({
                        "question_number": q_num,
                        "mark": q_mark,
                        "content": q_cnt,
                        "svg_code": q_svg
                    })
                    st.markdown("---")

                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if st.button("💾 حفظ التعديلات على هذه الورقة", key=f"save_exam_{exam_id}"):
                        updated_record = {
                            "subject": e_subject,
                            "year": e_year,
                            "term": e_term,
                            "stage": e_stage,
                            "questions_data": updated_q_list
                        }
                        update_cloud_exam(exam_id, updated_record)
                
                with col_btn2:
                    if st.button("🗑️ حذف الورقة الامتحانية بالكامل", key=f"del_exam_{exam_id}"):
                        delete_cloud_exam(exam_id)