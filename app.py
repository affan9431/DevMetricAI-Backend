from flask import Flask, render_template, request, jsonify, url_for, redirect
from pymongo import MongoClient
import pymongo
import pymupdf
import os
from dotenv import load_dotenv
import jwt
from flask_bcrypt import Bcrypt
import stripe
import datetime
from datetime import datetime, timedelta
from flask_cors import CORS
import fitz
import spacy
from spacy.matcher import PhraseMatcher
from languageList import skills_list
from questionGenerate import generate_coding_question
from questionGenerate import evaluate_user_code
from questionGenerate import generate_interview_question as generate_faang_interview_question
from questionGenerate import generate_aptitude_and_reasoning_questions as generate_faang_style_reasoning_questions
from questionGenerate import predict_domain_based_on_skills
from questionGenerate import predict_user_strength_and_weakness
import re
from bson import ObjectId
import json

from datetime import datetime

from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode
from flask_session import Session
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message


load_dotenv()  # Load .env file


current_time = datetime.now()

port = int(os.environ.get("PORT", 5000))


stripe_keys = {
    "secret_key": os.getenv("STRIPE_SECRET_KEY"),
    "publishable_key": os.getenv("STRIPE_PUBLIC_KEY"),
}


def extract_projects(text):
    # Split at "Projects" section
    project_section = re.split(r'(?i)\bProjects\b', text)
    if len(project_section) < 2:
        return []

    project_text = project_section[1]  # Get content after "Projects"

    # Stop at next section (like Experience, Education, etc.)
    project_text = re.split(
        r'(?i)\b(Experience|Education|Skills|Work History|ACHIEVEMENTS|Courses)\b', project_text)[0]

    # Extract project names and descriptions
    projects = []
    lines = project_text.strip().split("\n")
    i = 0
    while i < len(lines):
        if lines[i].strip():  # If line is not empty
            project_name = lines[i].strip()
            i += 1
            description = ""
            while i < len(lines) and lines[i].strip() and not re.match(r'^\b(Experience|Education|Skills|Work History|ACHIEVEMENTS|Courses)\b', lines[i], re.I):
                description += " " + lines[i].strip()
                i += 1
            projects.append(f"{project_name}: {description.strip()}")
        i += 1

    return projects


nlp = spacy.load("en_core_web_sm")

matcher = PhraseMatcher(nlp.vocab)
patterns = [nlp(skill) for skill in skills_list]
matcher.add("SKILL_MATCHER", patterns)

# ALl the constants
USER_API = "/api/users"
UPLOAD_FOLDER = './upload'
EXTRACTED_SKILLS = list()
DOMAIN = ""

# Call library function here
bcrypt = Bcrypt()


if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs("./upload")


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'affansayeed234@gmail.com'
app.config['MAIL_PASSWORD'] = 'xbrg apde iffy dajo'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False


mail = Mail(app)

s = URLSafeTimedSerializer(app.secret_key)

# Token generator


def generate_verification_token(email):
    """
    Generate a verification token for an email.
    """
    return s.dumps(email, salt="email-confirm")

# Token verifier


def confirm_verification_token(token, expiration=3600):
    """
    Confirm the verification token.

    Args:
        token (str): The token to confirm.
        expiration (int): Time in seconds before token expires. Default = 1 hour.

    Returns:
        str|None: Email if valid, None if invalid or expired.
    """
    try:
        email = s.loads(token, salt="email-confirm", max_age=expiration)
    except Exception:
        return None
    return email


# Add this to use filesystem-based session storage
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False

app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True  # Required for same-site None

# This initializes the session management
Session(app)

oauth = OAuth(app)


CORS(app, supports_credentials=True, origins=[
     "http://localhost:5173", "https://devmetricai.netlify.app"])


# Mongo Connection
client = MongoClient(os.getenv("MONGODBATLAS_URI"))
db = client["AiInterview"]
collection = db["users"]
companyCollection = db["companies"]
userResume = db["userResume"]
extractSkill = db["extractSkill"]
codeEvaluation = db["codeEvaluation"]
subscriptions = db["subscriptions"]
contactData = db["contact"]
reviewData = db["review"]
userCredits = db["userCredits"]

google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    access_token_url='https://oauth2.googleapis.com/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
    authorize_params=None,
    api_base_url='https://openidconnect.googleapis.com/v1/',
    client_kwargs={'scope': 'openid email profile'},
    jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

github = oauth.register(
    name='github',
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    api_base_url='https://api.github.com/',
    userinfo_endpoint='https://api.github.com/user',
    client_kwargs={'scope': 'user:email'},
)


@app.route('/')
def index():
    """Return a simple 'Hello World!' message."""
    return "Hello World!"


# ---- REDIRECT ROUTES ----
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google_login', _external=True)
    print("Redirect URI →", redirect_uri)

    return google.authorize_redirect(redirect_uri)


@app.route('/signup/google')
def signup_google():
    redirect_uri = url_for('authorize_google_signup', _external=True)
    print("Redirect URI →", redirect_uri)

    return google.authorize_redirect(redirect_uri)


@app.route('/authorize/google/login')
def authorize_google_login():
    # prod_frontend_url = os.getenv("FRONTEND_URL")
    dev_frontend_url = "http://localhost:5173"
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()

    email = user_info.get("email")

    user = collection.find_one({"email": email})
    if not user:
        error_params = urlencode({"error": "no_account"})
        return redirect(f"{dev_frontend_url}/signin?{error_params}")

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    jwt_token = jwt.encode({
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "picture": user.get("picture"),
        "location": user.get("location"),
        "yearOfExperiences": user.get("yearOfExperiences"),
        "bio": user.get("bio"),
        "socialLinks": user.get("socialLinks"),
        "preferredLocation": user.get("preferredLocation"),
        "exp": exp_timestamp  # ✅ standard JWT expiration claim
    }, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

    params = urlencode({"login_token": jwt_token})
    return redirect(f"{dev_frontend_url}/oauth-callback?{params}")


@app.route('/authorize/google/signup')
def authorize_google_signup():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()

    name = user_info.get("name")
    email = user_info.get("email")
    picture = user_info.get("picture")

    user = collection.find_one({"email": email})
    if not user:
        collection.insert_one({
            "name": name,
            "email": email,
            "role": "",
            "auth_type": "google",
            "picture": picture,
            "location": "",
            "preferredLocation": "",
            "yearOfExperiences": "",
            "bio": "",
            "socialLinks": [],
            "skills": []
        })

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    jwt_token = jwt.encode({
        "name": name,
        "email": email,
        "picture": picture,
        "expiredAt": exp_timestamp
    }, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

    # prod_frontend_url = os.getenv("FRONTEND_URL")
    dev_frontend_url = "http://localhost:5173"
    params = urlencode({"token": jwt_token})
    return redirect(f"{dev_frontend_url}/oauth-callback?{params}")


@app.route("/api/complete-profile", methods=["POST"])
def complete_profile():
    data = request.json

    email = data.get("email")
    role = data.get("role")
    location = data.get("location")
    yearOfExperiences = data.get("yearOfExperiences")
    preferredLocation = data.get("preferredLocation")

    # ✅ Update the user document
    collection.update_one(
        {"email": email},
        {"$set": {
            "role": role,
            "location": location,
            "yearOfExperiences": yearOfExperiences,
            "preferredLocation": preferredLocation
        }}
    )

    # ✅ Fetch the updated user from DB
    user = collection.find_one({"email": email})

    if not user:
        return jsonify({"status": False, "message": "User not found"}), 404

    # ✅ Set expiry timestamp
    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    # ✅ Create JWT with updated user info
    jwt_token = jwt.encode({
        "name": user.get("name"),
        "email": user.get("email"),
        "picture": user.get("picture"),
        "role": user.get("role"),
        "location": user.get("location"),
        "yearOfExperiences": user.get("yearOfExperiences"),
        "bio": user.get("bio"),
        "socialLinks": user.get("socialLinks"),
        "preferredLocation": user.get("preferredLocation"),
        "expiredAt": exp_timestamp
    }, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

    # ✅ Return response
    return jsonify({
        "status": True,
        "message": "Profile updated successfully",
        "token": jwt_token
    }), 200


@app.route("/login/github")
def login_github():
    redirect_uri = url_for("authorize_github_login", _external=True)
    return github.authorize_redirect(redirect_uri)


@app.route("/signup/github")
def signup_github():
    redirect_uri = url_for("authorize_github_signup", _external=True)
    return github.authorize_redirect(redirect_uri)


@app.route('/authorize/github/login')
def authorize_github_login():
    # prod_frontend_url = os.getenv("FRONTEND_URL")
    dev_frontend_url = "http://localhost:5173"
    token = github.authorize_access_token()
    resp = github.get('user')
    user_info = resp.json()

    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("login")
    avatar = user_info.get("avatar_url")

    # Fallback to get primary verified email
    if not email:
        emails_resp = github.get("user/emails")
        for e in emails_resp.json():
            if e.get("primary") and e.get("verified"):
                email = e.get("email")
                break

    if not email:
        # 👈 redirect with error
        return redirect(f"{dev_frontend_url}/signin?error=github-email")

    user = collection.find_one({"email": email})
    if not user:
        # 👈 toast this error on frontend
        return redirect(f"{dev_frontend_url}/signin?error=no-account")

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    jwt_token = jwt.encode({
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "picture": user.get("picture"),
        "location": user.get("location"),
        "yearOfExperiences": user.get("yearOfExperiences"),
        "bio": user.get("bio"),
        "socialLinks": user.get("socialLinks"),
        "preferredLocation": user.get("preferredLocation"),
        "expiredAt": exp_timestamp
    }, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

    return redirect(f"{dev_frontend_url}/oauth-callback?login_token={jwt_token}")


@app.route('/authorize/github/signup')
def authorize_github_signup():
    # prod_frontend_url = os.getenv("FRONTEND_URL")
    dev_frontend_url = "http://localhost:5173"
    token = github.authorize_access_token()
    resp = github.get('user')
    user_info = resp.json()

    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("login")
    avatar = user_info.get("avatar_url")

    # Fallback to get verified email
    if not email:
        emails_resp = github.get("user/emails")
        for e in emails_resp.json():
            if e.get("primary") and e.get("verified"):
                email = e.get("email")
                break

    if not email:
        return redirect(f"{dev_frontend_url}/signup?error=github-email")

    user = collection.find_one({"email": email})
    if not user:
        collection.insert_one({
            "name": name,
            "email": email,
            "role": "",
            "auth_type": "github",
            "picture": avatar,
            "location": "",
            "preferredLocation": "",
            "yearOfExperiences": "",
            "bio": "",
            "socialLinks": [],
            "skills": []
        })

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    jwt_token = jwt.encode({
        "name": name,
        "email": email,
        "picture": avatar,
        "expiredAt": exp_timestamp
    }, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

    return redirect(f"{dev_frontend_url}/oauth-callback?token={jwt_token}")


@app.route(f"{USER_API}/signup", methods=["POST"])
def signup():
    data = request.json

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    location = data.get("location")
    yearOfExperiences = data.get("yearOfExperiences")
    preferredLocation = data.get("preferredLocation")

    if not name or not email or not password or not role:
        return {"error": "No data provided"}, 400

    hashPassword = bcrypt.generate_password_hash(password).decode('utf-8')

    userData = {
        "name": name,
        "email": email,
        "role": role,
        "password": hashPassword,
        "auth_type": "credentials",
        "picture": "",
        "location": location,
        "preferredLocation": preferredLocation,
        "yearOfExperiences": yearOfExperiences,
        "bio": "",
        "socialLinks": [],
        "skills": []
    }

    collection.insert_one(userData)

    return {"success": True}, 201


@app.route(f"{USER_API}/login", methods=["POST"])
def login():
    data = request.json

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {"error": "No data provided"}, 400

    user = collection.find_one({"email": email})

    if not user or not bcrypt.check_password_hash(user["password"], password):
        return {"error": "Invalid email or password"}, 401

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())

    token = jwt.encode({"name": user["name"], "email": email, "role": user["role"],
                        "location": user["location"], "yearOfExperiences": user["yearOfExperiences"], "bio": user["bio"],
                        "socialLinks": user["socialLinks"], "preferredLocation": user["preferredLocation"],
                       "expiredAt": exp_timestamp}, os.getenv("JWT_SECRET_KEY"),
                       algorithm="HS256",)

    return {"success": True, "token": token, "message": "Login successful"}, 201


@app.route("/api/company/register", methods=["POST"])
def company_register():
    data = request.json
    email = data.get("email")

    # ✅ Check if company already exists
    if companyCollection.find_one({"email": email}):
        return jsonify({"message": "Email already registered"}), 400

    # ✅ Hash password before saving
    hashed_password = bcrypt.generate_password_hash(
        data.get("password")).decode('utf-8')

    # ✅ Save company with is_verified=False
    company = {
        "name": data.get("name"),
        "webUri": data.get("webUri"),
        "email": email,
        "industryType": data.get("industryType"),
        "location": data.get("location"),
        "password": hashed_password,
        "is_verified": False
    }
    result = companyCollection.insert_one(company)

    # ✅ Generate token
    token = generate_verification_token(email)
    verify_url = url_for("verify_email", token=token, _external=True)

    # ✅ Send verification email
    subject = "Verify Your Email - DevMetricAI"
    msg = Message(subject, sender="affansayeed234@gmail.com",
                  recipients=[email])
    msg.body = f"""
    Hi {data.get("name")},

    Thanks for signing up! Please verify your email by clicking the link below:

    {verify_url}

    This link will expire in 1 hour.
    """
    mail.send(msg)

    return jsonify({
        "message": "Registration successful. Verification email sent!",
        "company_id": str(result.inserted_id)
    }), 201


@app.route("/api/company/verify/<token>")
def verify_email(token):
    email = confirm_verification_token(token)

    if not email:
        return jsonify({"message": "Invalid or expired token"}), 400

    # ✅ Update company record
    result = companyCollection.update_one(
        {"email": email},
        {"$set": {"is_verified": True}}
    )

    if result.modified_count == 0:
        # Already verified
        company_data = companyCollection.find_one(
            {"email": email}, {"_id": 0, "password": 0})
    else:
        # Get company data after verification
        company_data = companyCollection.find_one(
            {"email": email}, {"_id": 0, "password": 0})

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())
    # Create JWT token
    payload = {
        "company": company_data,
        "expiredAt": exp_timestamp
    }
    token = jwt.encode(payload, os.getenv("SECRET_KEY"), algorithm="HS256")

    # Redirect to frontend with token and verified flag

    # prod_frontend_url = os.getenv("FRONTEND_URL")
    dev_frontend_url = "http://localhost:5173"

    frontend_url = f"{dev_frontend_url}/app/company?verified=true&token={token}"
    return redirect(frontend_url)


@app.route("/api/company/resend-verification", methods=["POST"])
def resend_verification():
    data = request.json
    email = data.get("email")

    company = companyCollection.find_one({"email": email})
    if not company:
        return jsonify({"message": "Company not found"}), 404

    if company.get("is_verified"):
        return jsonify({"message": "Email is already verified"}), 400

    # Generate token again
    token = generate_verification_token(email)
    verify_url = url_for("verify_email", token=token, _external=True)

    # Send email
    subject = "Resend: Verify Your Email - DevMetricAI"
    msg = Message(subject, sender="noreply@yourapp.com", recipients=[email])
    msg.body = f"""
    Hi {company.get("name")},

    Please verify your email again using the link below:

    {verify_url}

    This link will expire in 1 hour.
    """
    mail.send(msg)

    return jsonify({"message": "Verification email resent successfully!"}), 200


@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    email = request.headers.get("Email")
    resume = request.files["resume"]

    filepath = os.path.join(UPLOAD_FOLDER, resume.filename)
    resume.save(filepath)

    resume_text = ""
    with fitz.open(filepath) as doc:
        for page in doc:
            resume_text += page.get_text()

    userResume.insert_one({"email": email, "resume": resume_text})

    doc = nlp(resume_text)
    matches = matcher(doc)

    extracted_skills = [
        doc[start:end].text for match_id, start, end in matches]

    extracted_projects = extract_projects(resume_text)

    EXTRACTED_SKILLS = extracted_skills
    domain = predict_domain_based_on_skills(EXTRACTED_SKILLS)
    DOMAIN = domain
    # we have to store extracted_skill and domain in db
    extractSkill.insert_one(
        {"email": email, "skills": EXTRACTED_SKILLS, "domain": DOMAIN, "extracted_projects": extracted_projects})

    collection.update_one(
        {"email": email, }, {"$set": {"skills": EXTRACTED_SKILLS, "created_at": current_time}})

    question = generate_coding_question()
    os.remove(filepath)

    return jsonify({"message": "File uploaded successfully", "filename": resume.filename, "question": question})


@app.route("/api/review-codes", methods=["POST"])
def review_codes():
    data = request.json
    email = request.headers.get("Email")
    role = request.headers.get("Role")
    answer = evaluate_user_code(data)

    result = codeEvaluation.insert_one(
        {"email": email,
         "role": role,
         "code_review": answer,
         "reasoning_and_aptitude_review": "",
         "interview_review": "",
         "totalMarks": "",
         "created_at": current_time})

    cuurID = result.inserted_id
    print(cuurID)
    return jsonify({"cuurID": str(cuurID)})


@app.route("/api/generate-interview-question", methods=["POST"])
def generate_interview_question():
    answer = request.json
    email = request.headers.get("Email")
    stopInterview = request.headers.get("StopInterview")
    codeEvaluationID = request.headers.get("CodeEvaluationID")

    data = extractSkill.find_one({'email': email})
    skills = data['skills']
    domain = data['domain']
    project = data['extracted_projects'][0] if data['extracted_projects'] else None

    question = generate_faang_interview_question(
        answer, skills, domain, project, stopInterview)

    print(stopInterview)

    subscriptionData = None

    if (stopInterview == "false"):

        subscriptionData = subscriptions.find_one(
            {"email": email, "plan.status": "active"}
        )

    if subscriptionData:
        plan = subscriptionData.get("plan", {})
        plan_name = plan.get("name")

        # For One Shot: just deactivate after one use
        if plan_name == "One Shot":
            subscriptions.update_one(
                {"email": email, "plan.status": "active"},
                {"$set": {"plan.status": "inactive", "plan.interviews_allowed": 0}}
            )

        elif plan_name in ["Grind Mode", "Legend Mode"]:
            end_date_str = plan.get("end_date")

            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(
                        end_date_str.replace("Z", "+00:00"))
                    now = datetime.utcnow()

                    if now > end_date:
                        # Expired — deactivate
                        subscriptions.update_one(
                            {"email": email, "plan.status": "active"},
                            {"$set": {"plan.status": "inactive"}}
                        )
                except Exception as e:
                    print("Error parsing end_date:", e)

    # TODO: Calculate correct totalMarks

    codeEvaluation.update_one(
        {'_id': ObjectId(codeEvaluationID)}, {"$set": {"interview_review": question, "created_at": current_time}})

    doc = codeEvaluation.find_one({"_id": ObjectId(codeEvaluationID)})

    if doc:
        def safe_extract(json_str, key):
            if not json_str:
                return 0
            try:
                # Case 1: already a dict
                if isinstance(json_str, dict):
                    return json_str.get(key, 0)

                # Case 2: string with/without fences
                clean_str = re.sub(
                    r"^```(?:json)?\s*|\s*```$", "", json_str.strip())
                parsed = json.loads(clean_str)
                return parsed.get(key, 0)
            except Exception as e:
                print("Parse error:", e)
                return 0

        code_marks = safe_extract(doc.get("code_review"), "totalMarks")
        aptitude_marks = doc.get(
            "reasoning_and_aptitude_review", {}).get("totalMarks", 0)
        interview_marks = safe_extract(
            doc.get("interview_review"), "totalMarks")

        print("Code Review Marks:", code_marks)
        print("Reasoning & Aptitude Marks:", aptitude_marks)
        print("Interview Marks:", interview_marks)
        totalMarks = code_marks + aptitude_marks + interview_marks
        print("total", totalMarks)

        codeEvaluation.update_one(
            {'_id': ObjectId(codeEvaluationID)}, {"$set": {"totalMarks": totalMarks, "created_at": current_time}})

    return jsonify({"message": "Interview question generated successfully", "question": question})


@app.route('/api/get-interview-result')
def get_interview_result():
    codeEvaluationID_str = request.headers.get('CodeEvaluationID')
    email = request.headers.get('email')
    try:
        codeEvaluationID = ObjectId(codeEvaluationID_str)
        print("ccc: ", codeEvaluation)
        result = [doc for doc in codeEvaluation.find(
            {"email": email}, {"_id": 0})]
        resultById = list(codeEvaluation.find(
            {"_id": codeEvaluationID}, {"_id": 0}))

        return jsonify({"result": resultById, "results": result})

    except Exception as e:
        print("Invalid ObjectId:", e)
        return jsonify({"error": "Invalid CodeEvaluationID"}), 400


@app.route("/api/get-user-strength-and-weekness")
def get_user_strength_and_weekness():
    email = request.headers.get("Email")
    result = [doc for doc in codeEvaluation.find(
        {"email": email}, {"_id": 0})]
    strength_and_weekness = predict_user_strength_and_weakness(result)
    print("strength and weekness: ", strength_and_weekness)

    strength = strength_and_weekness.split("```javascript")[1]
    weeknees = strength_and_weekness.split("``````javascript")
    print(strength)
    print(weeknees)
    return jsonify({"message": "User strength and weekness predicted successfully", "result": strength_and_weekness})


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():

    stripe.api_key = stripe_keys["secret_key"]

    try:
        # Create new Checkout Session for the order

        data = request.json
        price = int(float(data.get("price")) * 100)

        reccuringData = data.get("subscriptionType")

        print(data.get("imageUrl"))
        checkout_session = stripe.checkout.Session.create(
            success_url="https://devmetricai.netlify.app/app/upload-resume?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://devmetricai.netlify.app",
            customer_email=data.get("email"),
            payment_method_types=["card"],
            mode="subscription" if reccuringData in [
                "month", "year"] else "payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": data.get("title"),
                            "images": [data.get("imageUrl")],
                        },
                        "recurring": {
                            "interval": reccuringData if reccuringData != "interview" else None
                        },
                        # Amount in cents: $9.99/month for example
                        "unit_amount": price,
                    },
                    "quantity": 1,
                }
            ]

        )
        return jsonify({"session": checkout_session, "title": data.get("title")})
    except Exception as e:
        print(e)
        return jsonify(error=str(e)), 403


@app.route("/api/create-subscription-details", methods=["POST"])
def create_subscription_details():
    # Create new subscription details for the order
    data = request.json
    print(data)

    # {'name': 'Affan Sayeed', 'email': 'affansayeed234@gmail.com', 'subscriptionTitle': 'One Shot'}

    userName = data.get("name")
    email = data.get("email")
    name = data.get("subscriptionTitle")

    # Get current UTC time
    start_date = datetime.utcnow()

    # Define default values
    end_date = None
    plan_type = "subscription"

    # Handle plan type and end date logic
    if name == "One Shot":
        plan_type = "one time payment"
        end_date = None
        interviews_allowed = 1
    elif name == "Grind Mode":
        end_date = start_date + timedelta(days=30)  # 1 month
        interviews_allowed = None
    elif name == "Legend Mode":
        end_date = start_date + timedelta(days=365)  # 1 year
        interviews_allowed = None

    # Format datetime as ISO strings
    start_date_iso = start_date.isoformat() + "Z"
    end_date_iso = end_date.isoformat() + "Z" if end_date else None

    # Final data structure
    finalData = {
        "user_name": userName,
        "email": email,
        "plan": {
            "name": name,
            "type": plan_type,
            "start_date": start_date_iso,
            "end_date": end_date_iso,
            "status": "active",
            "interviews_used": 0,
            "interviews_allowed": interviews_allowed  # unlimited
        }
    }

    newData = subscriptions.insert_one(finalData)

    return jsonify({"message": "Created Successfully", "inserted_id": str(newData.inserted_id)})


@app.route("/api/get-subscription-details")
def get_subscription_details():
    email = request.headers.get("Email")
    subscriptionData = subscriptions.find_one(
        {"email": email, "plan.status": "active"})
    if not subscriptionData:
        return jsonify({"message": "No active subscription found"}), 404

    print(subscriptionData["plan"])
    return jsonify({"message": "Subscription details found successfully", "result": str(subscriptionData["plan"])})


@app.route("/api/update-profile", methods=["PATCH"])
def update_profile():
    updated_data = request.json

    updated_name = updated_data.get("name")
    updated_role = updated_data.get("role")
    email = updated_data.get("email")
    image_url = updated_data.get("image")
    updated_bio = updated_data.get("bio")
    updated_location = updated_data.get("location")

    collection.update_one(
        {"email": email},
        {"$set": {"name": updated_name, "role": updated_role,
                  "picture": image_url, "bio": updated_bio, "location": updated_location}}
    )

    exp_time = datetime.utcnow() + timedelta(days=90)
    exp_timestamp = int(exp_time.timestamp())
    token = jwt.encode({"name": updated_name, "email": email, "role": updated_role, "picture": image_url,
                        "bio": updated_bio, "location": updated_location,
                       "expiredAt": exp_timestamp}, os.getenv("JWT_SECRET_KEY"),
                       algorithm="HS256",)

    return jsonify({"message": "Profile details updated successfully", "token": token})


@app.route("/api/get-data")
def get_data():
    email = request.headers.get("Email")
    print("Received Email:", email)

    data = collection.find({"email": email})
    result = []
    for doc in data:
        doc["_id"] = str(doc["_id"])
        result.append(doc)

    return jsonify({"data": result})


@app.route("/api/contact", methods=["POST"])
def contact():
    data = request.json
    contactData.insert_one(data)
    return jsonify({"message": "We recieved your message successfully!"})


@app.route("/api/generate-aptitude-and-reasoning-questions")
def generate_aptitude_and_reasoning_questions():
    response = generate_faang_style_reasoning_questions()
    return jsonify({"message": "Questions generated successfully", "questions": response})


@app.route("/api/total-marks-of-aptitude-and-reasoning", methods=['POST'])
def total_marks():
    data = request.json
    email = request.headers.get("Email")
    codeEvaluationID = request.headers.get("CodeEvaluationID")

    if not data:
        return jsonify({"error": "No JSON data received"}), 400

    totalMarks = data.get("totalMarks")

    if totalMarks < 10:
        overview = "Weak side – needs significant improvement."
    elif totalMarks < 15:
        overview = "Below average – keep practicing to improve."
    elif totalMarks < 20:
        overview = "Good – strong foundation, but can still improve."
    elif 20 <= totalMarks <= 25:
        overview = "Excellent – very strong reasoning and aptitude skills."
    else:
        overview = "Invalid marks received."

    final_result = {
        "overview": overview,
        "totalMarks": totalMarks
    }

    codeEvaluation.update_one(
        {'_id': ObjectId(codeEvaluationID)}, {"$set": {"reasoning_and_aptitude_review": final_result, "created_at": current_time}})

    return jsonify({"message": "Marks received", "totalMarks": totalMarks}), 200


@app.route("/api/review", methods=["POST"])
def review():
    data = request.json
    rating = data.get("rating")
    reviewText = data.get("reviewText")

    reviewData.insert_one(
        {"rating": rating, "reviewText": reviewText, "createdAt": current_time})

    return jsonify({"message": "Review submitted successfully!"}), 200


@app.route("/api/create-update-credits", methods=["POST"])
def create_update_credits():
    try:
        data = request.json
        name = data.get("name")
        email = data.get("email")
        creditsVal = data.get("credits", 0)
        history = data.get("history")

        print("HISTORY:", history)

        if not email:
            return jsonify({"error": "Email is required"}), 400

        if creditsVal == 0:
            return jsonify({"error": "Credits must be > 0"}), 400

        result = userCredits.update_one(
            {"email": email},
            {

                # only set on first insert
                "$setOnInsert": {"email": email, "name": name},
                "$inc": {"credits": creditsVal},
                "$push": {"history": history}
            },
            upsert=True
        )

        response = {"message": "Credits updated successfully"}

        if result.upserted_id:
            response["message"] = "Credits created successfully"
            response["id"] = str(result.upserted_id)

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/get-candidate-credits", methods=["POST"])
def get_candidate_credits():
    data = request.json
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    userCreditsData = userCredits.find_one({'email': email})

    if not userCreditsData:
        return jsonify({"error": "User not found"}), 404

    # Convert ObjectId to string (or remove it if not needed)
    userCreditsData["_id"] = str(userCreditsData["_id"])

    return jsonify(userCreditsData), 200


@app.route('/api/get-leaderboard-data')
def get_leaderboard_data():
    pipeline = [
        {
            "$lookup": {
                "from": "codeEvaluation",
                "localField": "email",
                "foreignField": "email",
                "as": "marksRecords"
            }
        },
        {
            "$addFields": {
                "highestMarks": {"$max": "$marksRecords.totalMarks"},
                "interviewCount": {"$size": "$marksRecords"}
            }
        },
        {
            "$project": {
                "_id": 0,
                "name": 1,
                "email": 1,
                "picture": 1,
                "location": 1,
                "highestMarks": 1,
                "interviewCount": 1
            }
        },
        {
            "$sort": {"highestMarks": -1}  # top scorers first
        }
    ]

    leaderboard_data = list(collection.aggregate(pipeline))
    return jsonify({"success": True, "leaderboardData": leaderboard_data})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=port)
