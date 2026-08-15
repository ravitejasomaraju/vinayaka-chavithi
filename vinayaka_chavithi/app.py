import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from database import get_connection

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-secret-key")


def close_conn(conn):
    try:
        if conn:
            conn.close()
    except Exception:
        pass


def is_admin():
    return str(session.get("role", "")).lower() == "admin"


def is_member():
    role = str(session.get("role", "")).lower()
    return role in ("member", "youth member", "youth_member")


def is_logged_in():
    return bool(session.get("user_id"))


# ==========================================================
# HOME
# ==========================================================
@app.route("/")
def home():
    timings = []
    programs = []
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, date, time, description
                FROM pooja_timings
                ORDER BY date, time
            """)
            timings = cur.fetchall()
            cur.execute("""
                SELECT id, program_name, program_date, program_time, description
                FROM programs
                ORDER BY program_date, program_time
            """)
            programs = cur.fetchall()
        conn.close()
    except Exception as e:
        print("HOME DATABASE ERROR:", e)
    return render_template("index.html", timings=timings, programs=programs)


# ==========================================================
# LOGIN
# ==========================================================
@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = None
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, role, password
                    FROM users
                    WHERE (phone = %s OR name = %s)
                      AND LOWER(role) = 'admin'
                    LIMIT 1
                """, (identifier, identifier))
                user = cur.fetchone()
            conn.close()
            if user and check_password_hash(user[4], password):
                session.clear()
                session["user_id"] = user[0]
                session["name"] = user[1]
                session["phone"] = user[2]
                session["role"] = user[3]
                return redirect(url_for("admin"))
            flash("Invalid admin username/phone or password.")
        except Exception as e:
            close_conn(conn)
            print("ADMIN LOGIN ERROR:", e)
            flash("Login error. Check Render logs.")
    return render_template("admin_login.html")


@app.route("/youth-login", methods=["GET", "POST"])
def youth_login():
    if request.method == "POST":
        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = None
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, role, password
                    FROM users
                    WHERE (phone = %s OR name = %s)
                      AND LOWER(role) IN ('member','youth member','youth_member')
                    LIMIT 1
                """, (identifier, identifier))
                user = cur.fetchone()
            conn.close()
            if user and check_password_hash(user[4], password):
                session.clear()
                session["user_id"] = user[0]
                session["name"] = user[1]
                session["phone"] = user[2]
                session["role"] = user[3]
                return redirect(url_for("member"))
            flash("Invalid member name/phone or password.")
        except Exception as e:
            close_conn(conn)
            print("MEMBER LOGIN ERROR:", e)
            flash("Login error. Check Render logs.")
    return render_template("youth_login.html")


# ==========================================================
# ADMIN DASHBOARD
# ==========================================================
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("admin_login"))

    total_members = total_users = 0
    total_donations = 0
    total_programs = 0
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*) FROM users
                WHERE LOWER(role) IN ('member','youth member','youth_member')
            """)
            total_members = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(amount),0) FROM donations WHERE payment_status = 'Paid'")
            total_donations = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM programs")
            total_programs = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        close_conn(conn)
        print("ADMIN DASHBOARD ERROR:", e)

    return render_template(
        "admin.html",
        name=session.get("name", "Admin"),
        total_members=total_members,
        total_users=total_users,
        total_donations=total_donations,
        total_programs=total_programs,
        google_meet_url=get_google_meet_url()
    )


@app.route("/admin-dashboard")
def admin_dashboard():
    return redirect(url_for("admin"))


# ==========================================================
# MEMBER DASHBOARD
# ==========================================================
@app.route("/member")
def member():
    if not is_member() and not is_admin():
        return redirect(url_for("youth_login"))

    my_donations = []
    my_total = 0
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            if is_member():
                cur.execute("""
                    SELECT id, donor_name, phone, amount, payment_method,
                           payment_status, donated_at
                    FROM donations
                    WHERE collected_by = %s
                    ORDER BY id DESC
                """, (session["user_id"],))
            else:
                cur.execute("""
                    SELECT id, donor_name, phone, amount, payment_method,
                           payment_status, donated_at
                    FROM donations
                    ORDER BY id DESC
                """)
            my_donations = cur.fetchall()
            if is_member():
                cur.execute("""
                    SELECT COALESCE(SUM(amount),0)
                    FROM donations
                    WHERE collected_by = %s AND payment_status = 'Paid'
                """, (session["user_id"],))
            else:
                cur.execute("""
                    SELECT COALESCE(SUM(amount),0)
                    FROM donations
                    WHERE payment_status = 'Paid'
                """)
            my_total = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        close_conn(conn)
        print("MEMBER DASHBOARD ERROR:", e)

    return render_template(
        "member.html",
        name=session.get("name", "Member"),
        my_donations=my_donations,
        my_total=my_total
    )


@app.route("/youth-dashboard")
def youth_dashboard():
    return redirect(url_for("member"))


# ==========================================================
# MEMBERS MANAGEMENT
# ==========================================================
@app.route("/admin/members", methods=["GET", "POST"])
def members():
    if not is_admin():
        return redirect(url_for("admin_login"))

    conn = None
    message = None
    error = None
    try:
        conn = get_connection()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "")
            if not name or not phone or not password:
                error = "Name, phone and password are required."
            else:
                from werkzeug.security import generate_password_hash
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (name, phone, role, password)
                        VALUES (%s, %s, 'Youth Member', %s)
                    """, (name, phone, generate_password_hash(password)))
                conn.commit()
                message = "Member added successfully."

        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, phone, role
                FROM users
                WHERE LOWER(role) IN ('member','youth member','youth_member')
                ORDER BY id DESC
            """)
            member_list = cur.fetchall()
        conn.close()
    except Exception as e:
        close_conn(conn)
        print("MEMBERS ERROR:", e)
        error = "Unable to manage members: " + str(e)
        member_list = []

    return render_template("members.html", members=member_list, message=message, error=error)


@app.route("/admin/members/delete/<int:user_id>", methods=["POST"])
def delete_member(user_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s AND LOWER(role) IN ('member','youth member','youth_member')", (user_id,))
        conn.commit()
        conn.close()
        flash("Member deleted successfully.")
    except Exception as e:
        close_conn(conn)
        print("DELETE MEMBER ERROR:", e)
        flash("Unable to delete member.")
    return redirect(url_for("members"))


# ==========================================================
# DONATIONS
# ==========================================================
@app.route("/member/collect-donation", methods=["GET", "POST"])
@app.route("/collect-donation", methods=["GET", "POST"])
def collect_donation():
    if not is_member() and not is_admin():
        return redirect(url_for("youth_login"))
    conn = None
    error = None
    message = None
    try:
        conn = get_connection()
        if request.method == "POST":
            donor_name = request.form.get("donor_name", "").strip()
            phone = request.form.get("phone", "").strip()
            amount = request.form.get("amount", "").strip()
            payment_method = request.form.get("payment_method", "Cash").strip()
            payment_status = request.form.get("payment_status", "Paid").strip()
            if not donor_name or not amount:
                error = "Donor name and amount are required."
            else:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO donations
                        (donor_name, phone, amount, payment_method,
                         payment_status, collected_by)
                        VALUES (%s,%s,%s,%s,%s,%s)
                    """, (donor_name, phone, amount, payment_method,
                          payment_status, session.get("user_id")))
                conn.commit()
                message = "Donation saved successfully."

        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, donor_name, phone, amount, payment_method,
                       payment_status, donated_at, collected_by
                FROM donations
                ORDER BY id DESC
            """)
            donation_list = cur.fetchall()
            cur.execute("""
                SELECT COALESCE(SUM(amount),0)
                FROM donations
                WHERE payment_status='Paid'
            """)
            total_collection = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        close_conn(conn)
        print("COLLECT DONATION ERROR:", e)
        error = str(e)
        donation_list = []
        total_collection = 0

    return render_template(
        "collect_donation.html",
        donations=donation_list,
        total_collection=total_collection,
        error=error,
        message=message,
        admin_mode=is_admin()
    )


@app.route("/admin/donations")
def admin_donations():
    if not is_admin():
        return redirect(url_for("admin_login"))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, donor_name, phone, amount, payment_method,
                       payment_status, donated_at, collected_by
                FROM donations ORDER BY id DESC
            """)
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        close_conn(conn)
        print("ADMIN DONATIONS ERROR:", e)
        rows = []
    return render_template("donations.html", donations=rows)


@app.route("/admin/donations/edit/<int:donation_id>", methods=["GET", "POST"])
def edit_donation(donation_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    conn = None
    try:
        conn = get_connection()
        if request.method == "POST":
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE donations
                    SET donor_name=%s, phone=%s, amount=%s,
                        payment_method=%s, payment_status=%s
                    WHERE id=%s
                """, (
                    request.form.get("donor_name", "").strip(),
                    request.form.get("phone", "").strip(),
                    request.form.get("amount", "").strip(),
                    request.form.get("payment_method", "Cash"),
                    request.form.get("payment_status", "Paid"),
                    donation_id
                ))
            conn.commit()
            conn.close()
            return redirect(url_for("admin_donations"))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, donor_name, phone, amount, payment_method,
                       payment_status, donated_at, collected_by
                FROM donations WHERE id=%s
            """, (donation_id,))
            donation = cur.fetchone()
        conn.close()
        if not donation:
            return "Donation not found", 404
        return render_template("edit_donation.html", donation=donation)
    except Exception as e:
        close_conn(conn)
        print("EDIT DONATION ERROR:", e)
        return render_template("edit_donation.html", donation=[donation_id,"","",0,"Cash","Paid",None,None], error=str(e))


@app.route("/admin/donations/delete/<int:donation_id>", methods=["POST"])
def delete_donation(donation_id):
    if not is_admin():
        return redirect(url_for("admin_login"))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM donations WHERE id=%s", (donation_id,))
        conn.commit()
        conn.close()
        flash("Donation deleted successfully.")
    except Exception as e:
        close_conn(conn)
        print("DELETE DONATION ERROR:", e)
        flash("Unable to delete donation.")
    return redirect(url_for("admin_donations"))


# ==========================================================
# PUBLIC DONATIONS
# ==========================================================
@app.route("/donations", methods=["GET", "POST"])
def donations():
    return redirect(url_for("admin_donations")) if is_admin() else redirect(url_for("collect_donation"))


# ==========================================================
# POOJA + PROGRAMS
# ==========================================================
@app.route("/add-program", methods=["POST"])
def add_program():
    if not is_admin(): return redirect(url_for("admin_login"))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO programs(program_name, program_date, program_time, description)
                VALUES(%s,%s,%s,%s)
            """, (request.form.get("program_name",""), request.form.get("program_date",""), request.form.get("program_time",""), request.form.get("description","")))
        conn.commit(); conn.close()
    except Exception as e:
        close_conn(conn); print("ADD PROGRAM ERROR:", e)
    return redirect(url_for("admin"))


@app.route("/delete-program/<int:program_id>", methods=["POST"])
def delete_program(program_id):
    if not is_admin(): return redirect(url_for("admin_login"))
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur: cur.execute("DELETE FROM programs WHERE id=%s",(program_id,))
        conn.commit(); conn.close()
    except Exception as e: close_conn(conn); print("DELETE PROGRAM ERROR:",e)
    return redirect(url_for("admin"))


@app.route("/add-timing", methods=["POST"])
def add_timing():
    if not is_admin(): return redirect(url_for("admin_login"))
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO pooja_timings(date,time,description) VALUES(%s,%s,%s)",(request.form.get("date",""),request.form.get("time",""),request.form.get("description","")))
        conn.commit(); conn.close()
    except Exception as e: close_conn(conn); print("ADD TIMING ERROR:",e)
    return redirect(url_for("admin"))


@app.route("/delete-timing/<int:timing_id>", methods=["POST"])
def delete_timing(timing_id):
    if not is_admin(): return redirect(url_for("admin_login"))
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur: cur.execute("DELETE FROM pooja_timings WHERE id=%s",(timing_id,))
        conn.commit(); conn.close()
    except Exception as e: close_conn(conn); print("DELETE TIMING ERROR:",e)
    return redirect(url_for("admin"))


@app.route("/pooja-timings")
def pooja_timings():
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id,date,time,description FROM pooja_timings ORDER BY date,time")
            rows=cur.fetchall()
        conn.close()
    except Exception as e:
        close_conn(conn); print("POOJA ERROR:",e); rows=[]
    return render_template("pooja_timings.html", timings=rows)


# ==========================================================
# PREVIOUS CELEBRATIONS
# ==========================================================
@app.route("/previous-celebrations")
def previous_celebrations():
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id,year,title,description,image_url,video_url FROM previous_celebrations ORDER BY year DESC,id DESC")
            rows=cur.fetchall()
        conn.close()
    except Exception as e:
        close_conn(conn); print("PREVIOUS CELEBRATIONS ERROR:",e); rows=[]
    return render_template("previous_celebrations.html", celebrations=rows)


@app.route("/admin/celebrations", methods=["GET","POST"])
def admin_celebrations():
    if not is_admin(): return redirect(url_for("admin_login"))
    message=None; error=None; conn=None
    try:
        conn=get_connection()
        if request.method=="POST":
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO previous_celebrations(year,title,description,image_url,video_url)
                    VALUES(%s,%s,%s,%s,%s)
                """,(request.form.get("year"),request.form.get("title",""),request.form.get("description",""),request.form.get("image_url",""),request.form.get("video_url","")))
            conn.commit(); message="Celebration added successfully."
        with conn.cursor() as cur:
            cur.execute("SELECT id,year,title,description,image_url,video_url FROM previous_celebrations ORDER BY year DESC,id DESC")
            rows=cur.fetchall()
        conn.close()
    except Exception as e:
        close_conn(conn); print("ADMIN CELEBRATIONS ERROR:",e); error=str(e); rows=[]
    return render_template("admin_celebrations.html",celebrations=rows,message=message,error=error)


@app.route("/admin/celebrations/delete/<int:celebration_id>", methods=["POST"])
def delete_celebration(celebration_id):
    if not is_admin(): return redirect(url_for("admin_login"))
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur: cur.execute("DELETE FROM previous_celebrations WHERE id=%s",(celebration_id,))
        conn.commit(); conn.close()
    except Exception as e: close_conn(conn); print("DELETE CELEBRATION ERROR:",e)
    return redirect(url_for("admin_celebrations"))


# ==========================================================
# SHARED MEMBER CHAT
# ==========================================================
@app.route("/member/chat", methods=["GET","POST"])
def member_chat():
    if not is_logged_in(): return redirect(url_for("login"))
    if request.method=="POST":
        msg=request.form.get("message","").strip()
        if msg:
            conn=None
            try:
                conn=get_connection()
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO member_messages(sender_id,sender_name,message) VALUES(%s,%s,%s)",(session["user_id"],session.get("name","User"),msg))
                conn.commit(); conn.close()
            except Exception as e: close_conn(conn); print("CHAT SEND ERROR:",e)
        return redirect(url_for("member_chat"))
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id,sender_id,sender_name,message,created_at FROM member_messages ORDER BY created_at ASC")
            rows=cur.fetchall()
        conn.close()
    except Exception as e: close_conn(conn); print("CHAT LOAD ERROR:",e); rows=[]
    return render_template("member_chat.html",messages=rows)


@app.route("/member/chat/messages")
def member_chat_messages():
    if not is_logged_in(): return jsonify(error="Not logged in"),401
    conn=None
    try:
        conn=get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id,sender_id,sender_name,message,created_at FROM member_messages ORDER BY created_at ASC")
            rows=cur.fetchall()
        conn.close()
        return jsonify(messages=[{"id":r[0],"sender_id":r[1],"sender_name":r[2],"message":r[3],"created_at":r[4].strftime("%d-%m-%Y %I:%M %p") if r[4] else ""} for r in rows])
    except Exception as e:
        close_conn(conn); print("CHAT API ERROR:",e); return jsonify(error=str(e)),500


# ==========================================================
# GOOGLE MEET SETTINGS
# ==========================================================
def get_google_meet_url():
    """Return the shared Google Meet URL saved by the admin.

    The database value is preferred. GOOGLE_MEET_URL remains as a
    fallback so an existing Render deployment continues to work.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS google_meet_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    meet_url TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("SELECT meet_url FROM google_meet_settings WHERE id = 1")
            row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception as e:
        close_conn(conn)
        print("GET GOOGLE MEET URL ERROR:", e)

    return os.environ.get("GOOGLE_MEET_URL", "").strip()


@app.route("/admin/google-meet", methods=["POST"])
def admin_google_meet():
    if not is_admin():
        return redirect(url_for("admin_login"))

    meet_url = request.form.get("meet_url", "").strip()

    if not meet_url:
        flash("Please enter a Google Meet link.")
        return redirect(url_for("admin"))

    if not (meet_url.startswith("https://meet.google.com/") or
            meet_url.startswith("http://meet.google.com/")):
        flash("Please enter a valid Google Meet URL starting with https://meet.google.com/")
        return redirect(url_for("admin"))

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS google_meet_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    meet_url TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                INSERT INTO google_meet_settings (id, meet_url, updated_at)
                VALUES (1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    meet_url = EXCLUDED.meet_url,
                    updated_at = CURRENT_TIMESTAMP
            """, (meet_url,))
        conn.commit()
        conn.close()
        flash("Google Meet link updated successfully.")
    except Exception as e:
        close_conn(conn)
        print("SAVE GOOGLE MEET URL ERROR:", e)
        flash("Unable to save Google Meet link: " + str(e))

    return redirect(url_for("admin"))


# ==========================================================
# VIDEO CONFERENCE
# ==========================================================
@app.route("/video-conference")
def video_conference():
    if not is_logged_in():
        return redirect(url_for("login"))

    google_meet_url = get_google_meet_url()

    return render_template(
        "video_conference.html",
        name=session.get("name", "User"),
        role=session.get("role"),
        google_meet_url=google_meet_url
    )


# ==========================================================
# LOGOUT
# ==========================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.errorhandler(500)
def internal_error(error):
    print("INTERNAL SERVER ERROR:",error)
    return "<h1>Internal Server Error</h1><p>Check Render logs for details.</p>",500


if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
