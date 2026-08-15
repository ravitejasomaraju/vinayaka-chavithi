import os

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from database import get_connection


app = Flask(__name__)

# ==========================================================
# SECRET KEY
# ==========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-secret-key"
)


# ==========================================================
# HOME
# ==========================================================

@app.route("/")
def home():

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    pooja_name,
                    pooja_date,
                    start_time,
                    end_time,
                    description
                FROM pooja_timings
                ORDER BY pooja_date ASC, start_time ASC
            """)

            timings = cur.fetchall()

        return render_template(
            "index.html",
            timings=timings
        )

    except Exception as e:

        print("HOME ERROR:", e)

        return render_template(
            "index.html",
            timings=[]
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# LOGIN
# ==========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not phone or not password:

            return render_template(
                "login.html",
                error="Phone number and password are required."
            )

        conn = None

        try:

            conn = get_connection()

            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT
                        id,
                        name,
                        password,
                        role
                    FROM users
                    WHERE phone = %s
                    """,
                    (phone,)
                )

                user = cur.fetchone()

            if user is None:

                return render_template(
                    "login.html",
                    error="Invalid phone number or password."
                )

            user_id = user[0]
            name = user[1]
            password_hash = user[2]
            role = user[3]

            if not check_password_hash(
                password_hash,
                password
            ):

                return render_template(
                    "login.html",
                    error="Invalid phone number or password."
                )

            session.clear()

            session["user_id"] = user_id
            session["name"] = name
            session["role"] = role

            if role == "admin":

                return redirect(
                    url_for("admin")
                )

            if role == "member":

                return redirect(
                    url_for("member")
                )

            session.clear()

            return render_template(
                "login.html",
                error="Invalid user role."
            )

        except Exception as e:

            print("LOGIN ERROR:", e)

            return render_template(
                "login.html",
                error="Database error: " + str(e)
            )

        finally:

            if conn:
                conn.close()

    return render_template("login.html")


# ==========================================================
# ADMIN DASHBOARD
# ==========================================================

@app.route("/admin")
def admin():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cur:

            # Total users
            cur.execute("""
                SELECT COUNT(*)
                FROM users
            """)

            total_users = cur.fetchone()[0]

            # Total members
            cur.execute("""
                SELECT COUNT(*)
                FROM users
                WHERE role = 'member'
            """)

            total_members = cur.fetchone()[0]

            # Total donations
            cur.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM donations
                WHERE payment_status = 'Paid'
            """)

            total_donations = cur.fetchone()[0]

            # Total programs
            cur.execute("""
                SELECT COUNT(*)
                FROM programs
            """)

            total_programs = cur.fetchone()[0]

        return render_template(
            "admin.html",
            name=session.get("name"),
            total_users=total_users,
            total_members=total_members,
            total_donations=total_donations,
            total_programs=total_programs
        )

    except Exception as e:

        print("ADMIN ERROR:", e)

        return "Admin dashboard error: " + str(e)

    finally:

        if conn:
            conn.close()


# ==========================================================
# ADMIN MEMBERS
# ==========================================================

@app.route(
    "/admin/members",
    methods=["GET", "POST"]
)
def admin_members():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    message = None
    error = None

    conn = None

    try:

        conn = get_connection()

        # --------------------------------------------------
        # ADD MEMBER
        # --------------------------------------------------

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            password = request.form.get(
                "password",
                ""
            )

            if not name:

                error = "Member name is required."

            elif not phone:

                error = "Phone number is required."

            elif not password:

                error = "Password is required."

            else:

                password_hash = generate_password_hash(
                    password
                )

                with conn.cursor() as cur:

                    cur.execute(
                        """
                        SELECT id
                        FROM users
                        WHERE phone = %s
                        """,
                        (phone,)
                    )

                    existing = cur.fetchone()

                    if existing:

                        error = (
                            "A user with this phone number "
                            "already exists."
                        )

                    else:

                        cur.execute(
                            """
                            INSERT INTO users
                            (
                                name,
                                phone,
                                password,
                                role
                            )
                            VALUES
                            (
                                %s,
                                %s,
                                %s,
                                'member'
                            )
                            """,
                            (
                                name,
                                phone,
                                password_hash
                            )
                        )

                        conn.commit()

                        message = (
                            "Youth member added successfully!"
                        )

        # --------------------------------------------------
        # GET MEMBERS
        # --------------------------------------------------

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    phone,
                    role,
                    created_at
                FROM users
                ORDER BY id DESC
            """)

            members = cur.fetchall()

        return render_template(
            "members.html",
            members=members,
            message=message,
            error=error
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "ADMIN MEMBERS ERROR:",
            e
        )

        return (
            "Admin members error: "
            + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# ADMIN DELETE MEMBER
# ==========================================================

@app.route("/admin/delete-member/<int:user_id>", methods=["POST"])
def delete_member(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    if user_id == session.get("user_id"):
        return "Admin account cannot be deleted.", 403

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()

            if not user:
                return "Member not found.", 404

            if user[0] == "admin":
                return "Admin account cannot be deleted.", 403

            # Keep old donation records, but remove the deleted
            # member reference before deleting the member account.
            cur.execute(
                """
                UPDATE donations
                SET collected_by = NULL
                WHERE collected_by = %s
                """,
                (user_id,)
            )

            cur.execute(
                "DELETE FROM users WHERE id = %s AND role = 'member'",
                (user_id,)
            )

        conn.commit()
        return redirect(url_for("admin_members"))

    except Exception as e:
        if conn:
            conn.rollback()
        print("DELETE MEMBER ERROR:", e)
        return "Delete member error: " + str(e), 500

    finally:
        if conn:
            conn.close()


# ==========================================================
# MEMBER DASHBOARD
# ==========================================================

@app.route("/member")
def member():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "member":
        return redirect(url_for("login"))

    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    donor_name,
                    phone,
                    amount,
                    payment_method,
                    payment_status,
                    donated_at
                FROM donations
                WHERE collected_by = %s
                ORDER BY id DESC
                """,
                (session["user_id"],)
            )

            my_donations = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM donations
                WHERE collected_by = %s
                AND payment_status = 'Paid'
                """,
                (session["user_id"],)
            )

            my_total = cur.fetchone()[0]

        return render_template(
            "member.html",
            name=session.get("name"),
            my_donations=my_donations,
            my_total=my_total
        )

    except Exception as e:

        print(
            "MEMBER ERROR:",
            e
        )

        return (
            "Member dashboard error: "
            + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# MEMBER COLLECT DONATION
# ==========================================================

@app.route("/collect-donation", methods=["GET", "POST"])
def collect_donation():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "member":
        return "Unauthorized", 403

    message = None
    error = None
    conn = None

    try:
        if request.method == "POST":

            donor_name = request.form.get("donor_name", "").strip()
            phone = request.form.get("phone", "").strip()
            amount_text = request.form.get("amount", "").strip()
            payment_method = request.form.get("payment_method", "Cash").strip()
            payment_status = request.form.get("payment_status", "Paid").strip()

            if not donor_name:
                error = "Donor name is required."

            elif not amount_text:
                error = "Donation amount is required."

            else:
                try:
                    amount = float(amount_text)
                    if amount <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    error = "Enter a valid donation amount greater than 0."

            if not error:
                conn = get_connection()

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO donations
                        (
                            donor_name,
                            phone,
                            amount,
                            payment_method,
                            payment_status,
                            collected_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            donor_name,
                            phone,
                            amount,
                            payment_method,
                            payment_status,
                            session["user_id"]
                        )
                    )

                conn.commit()

                return redirect(url_for("member"))

        return render_template(
            "collect_donation.html",
            message=message,
            error=error
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print("COLLECT DONATION ERROR:", e)

        return render_template(
            "collect_donation.html",
            message=None,
            error="Could not save donation: " + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# ADMIN MANAGE DONATIONS
# ==========================================================

@app.route("/admin/donations")
def admin_donations():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    d.id,
                    d.donor_name,
                    d.phone,
                    d.amount,
                    d.payment_method,
                    d.payment_status,
                    d.donated_at,
                    COALESCE(u.name, 'Deleted Member')
                FROM donations d
                LEFT JOIN users u
                    ON d.collected_by = u.id
                ORDER BY d.id DESC
                """
            )

            donation_list = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM donations
                WHERE payment_status = 'Paid'
                """
            )

            total_collection = cur.fetchone()[0]

        return render_template(
            "donations.html",
            donations=donation_list,
            total_collection=total_collection,
            admin_mode=True
        )

    except Exception as e:

        print("ADMIN DONATIONS ERROR:", e)

        return "Admin donations error: " + str(e), 500

    finally:

        if conn:
            conn.close()


# ==========================================================
# ADMIN EDIT DONATION
# ==========================================================

@app.route("/admin/donations/edit/<int:donation_id>", methods=["GET", "POST"])
def edit_donation(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    conn = None

    try:
        conn = get_connection()

        if request.method == "POST":
            donor_name = request.form.get("donor_name", "").strip()
            phone = request.form.get("phone", "").strip()
            amount = request.form.get("amount", "").strip()
            payment_method = request.form.get("payment_method", "Cash").strip()
            payment_status = request.form.get("payment_status", "Paid").strip()

            if not donor_name or not amount:
                return render_template("edit_donation.html", donation=None,
                                       error="Donor name and amount are required.")

            try:
                amount_value = float(amount)
                if amount_value <= 0:
                    raise ValueError
            except ValueError:
                return render_template("edit_donation.html", donation=None,
                                       error="Enter a valid amount greater than 0.")

            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE donations
                    SET donor_name=%s, phone=%s, amount=%s,
                        payment_method=%s, payment_status=%s
                    WHERE id=%s
                """, (donor_name, phone, amount_value, payment_method,
                      payment_status, donation_id))

                if cur.rowcount == 0:
                    conn.rollback()
                    return "Donation not found.", 404

            conn.commit()
            return redirect(url_for("admin_donations"))

        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, donor_name, phone, amount,
                       payment_method, payment_status, donated_at
                FROM donations
                WHERE id=%s
            """, (donation_id,))
            donation = cur.fetchone()

        if not donation:
            return "Donation not found.", 404

        return render_template("edit_donation.html",
                               donation=donation, error=None)

    except Exception as e:
        if conn:
            conn.rollback()
        print("EDIT DONATION ERROR:", e)
        return "Edit donation error: " + str(e), 500

    finally:
        if conn:
            conn.close()


# ==========================================================
# ADMIN DELETE DONATION
# ==========================================================

@app.route("/admin/donations/delete/<int:donation_id>", methods=["POST"])
def delete_donation(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM donations WHERE id=%s",
                (donation_id,)
            )

            if cur.fetchone() is None:
                return "Donation not found.", 404

            cur.execute(
                "DELETE FROM donations WHERE id=%s",
                (donation_id,)
            )

        conn.commit()
        return redirect(url_for("admin_donations"))

    except Exception as e:
        if conn:
            conn.rollback()
        print("DELETE DONATION ERROR:", e)
        return "Delete donation error: " + str(e), 500

    finally:
        if conn:
            conn.close()


# ==========================================================
# ADMIN POOJA TIMINGS
# ==========================================================

@app.route(
    "/admin/pooja-timings",
    methods=["GET", "POST"]
)
def admin_pooja_timings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    message = None
    error = None

    conn = None

    try:

        conn = get_connection()

        # --------------------------------------------------
        # ADD POOJA TIMING
        # --------------------------------------------------

        if request.method == "POST":

            pooja_name = request.form.get(
                "pooja_name",
                ""
            ).strip()

            pooja_date = request.form.get(
                "pooja_date",
                ""
            ).strip()

            start_time = request.form.get(
                "start_time",
                ""
            ).strip()

            end_time = request.form.get(
                "end_time",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            if not pooja_name:

                error = "Pooja name is required."

            elif not pooja_date:

                error = "Pooja date is required."

            elif not start_time:

                error = "Start time is required."

            else:

                with conn.cursor() as cur:

                    cur.execute(
                        """
                        INSERT INTO pooja_timings
                        (
                            pooja_name,
                            pooja_date,
                            start_time,
                            end_time,
                            description
                        )
                        VALUES
                        (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            pooja_name,
                            pooja_date,
                            start_time,
                            end_time
                            if end_time
                            else None,
                            description
                            if description
                            else None
                        )
                    )

                conn.commit()

                message = (
                    "Pooja timing added successfully!"
                )

        # --------------------------------------------------
        # GET TIMINGS
        # --------------------------------------------------

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    pooja_name,
                    pooja_date,
                    start_time,
                    end_time,
                    description
                FROM pooja_timings
                ORDER BY
                    pooja_date ASC,
                    start_time ASC
                """
            )

            timings = cur.fetchall()

        return render_template(
            "admin_pooja_timings.html",
            timings=timings,
            message=message,
            error=error
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "POOJA TIMINGS ERROR:",
            e
        )

        return (
            "Pooja timings error: "
            + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# DELETE POOJA TIMING
# ==========================================================

@app.route(
    "/admin/pooja-timings/delete/<int:timing_id>",
    methods=["POST"]
)
def delete_pooja_timing(timing_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                DELETE FROM pooja_timings
                WHERE id = %s
                """,
                (timing_id,)
            )

        conn.commit()

        return redirect(
            url_for(
                "admin_pooja_timings"
            )
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "DELETE POOJA ERROR:",
            e
        )

        return (
            "Delete pooja timing error: "
            + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# PUBLIC POOJA TIMINGS
# ==========================================================

@app.route("/pooja-timings")
def public_pooja_timings():

    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    pooja_name,
                    pooja_date,
                    start_time,
                    end_time,
                    description
                FROM pooja_timings
                ORDER BY
                    pooja_date ASC,
                    start_time ASC
                """
            )

            timings = cur.fetchall()

        return render_template(
            "pooja_timings.html",
            timings=timings
        )

    except Exception as e:

        print(
            "PUBLIC POOJA ERROR:",
            e
        )

        return (
            "Pooja timings error: "
            + str(e)
        )

    finally:

        if conn:
            conn.close()


# ==========================================================
# LOGOUT
# ==========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )

# ==========================================================
# PREVIOUS YEAR CELEBRATIONS - ADMIN
# ==========================================================

@app.route("/admin/celebrations", methods=["GET", "POST"])
def admin_celebrations():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    conn = None
    message = None
    error = None

    try:
        conn = get_connection()

        # ------------------------------------------
        # ADD CELEBRATION
        # ------------------------------------------
        if request.method == "POST":

            year = request.form.get("year", "").strip()
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            video_url = request.form.get("video_url", "").strip()
            image_url = request.form.get("image_url", "").strip()

            if not year or not title:
                error = "Year and title are required."

            elif not video_url:
                error = "Google Drive video link is required."

            else:

                # Convert Google Drive sharing URL
                # into an embeddable URL
                if "/file/d/" in video_url:

                    try:
                        file_id = video_url.split("/file/d/")[1].split("/")[0]

                        video_url = (
                            "https://drive.google.com/file/d/"
                            + file_id
                            + "/preview"
                        )

                    except Exception:
                        error = "Invalid Google Drive video link."

                if not error:

                    with conn.cursor() as cur:

                        cur.execute("""
                            INSERT INTO previous_celebrations
                            (
                                year,
                                title,
                                description,
                                image_url,
                                video_url
                            )
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            int(year),
                            title,
                            description,
                            image_url,
                            video_url
                        ))

                    conn.commit()

                    message = "Celebration added successfully."

        # ------------------------------------------
        # GET ALL CELEBRATIONS
        # ------------------------------------------

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    year,
                    title,
                    description,
                    image_url,
                    video_url,
                    created_at
                FROM previous_celebrations
                ORDER BY year DESC, id DESC
            """)

            celebrations = cur.fetchall()

        return render_template(
            "admin_celebrations.html",
            celebrations=celebrations,
            message=message,
            error=error
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print("CELEBRATIONS ERROR:", e)

        return "Celebrations error: " + str(e)

    finally:

        if conn:
            conn.close()


# ==========================================================
# DELETE PREVIOUS CELEBRATION
# ==========================================================

@app.route(
    "/admin/celebrations/delete/<int:celebration_id>",
    methods=["POST"]
)
def delete_celebration(celebration_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Unauthorized", 403

    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM previous_celebrations
                WHERE id = %s
            """, (celebration_id,))

        conn.commit()

        return redirect(
            url_for("admin_celebrations")
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print("DELETE CELEBRATION ERROR:", e)

        return "Delete celebration error: " + str(e)

    finally:

        if conn:
            conn.close()

@app.route("/previous-celebrations")
def previous_celebrations():

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    year,
                    title,
                    description,
                    image_url,
                    video_url,
                    created_at
                FROM previous_celebrations
                ORDER BY year DESC, id DESC
            """)

            celebrations = cur.fetchall()

        return render_template(
            "previous_celebrations.html",
            celebrations=celebrations
        )

    except Exception as e:
        print("PUBLIC CELEBRATIONS ERROR:", e)
        return "Previous celebrations error: " + str(e)

    finally:
        if conn:
            conn.close()
@app.route("/member/chat/messages")
def member_chat_messages():

    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    if session.get("role") != "member":
        return {"error": "Unauthorized"}, 403

    conn = None

    try:
        conn = get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    sender_id,
                    sender_name,
                    message,
                    created_at
                FROM member_messages
                ORDER BY created_at ASC
            """)

            rows = cur.fetchall()

        messages = []

        for row in rows:
            messages.append({
                "id": row[0],
                "sender_id": row[1],
                "sender_name": row[2],
                "message": row[3],
                "created_at": row[4].strftime(
                    "%d-%m-%Y %I:%M %p"
                )
            })

        return {
            "messages": messages
        }

    except Exception as e:

        print("CHAT MESSAGES ERROR:", e)

        return {
            "error": str(e)
        }, 500

    finally:

        if conn:
            conn.close()
# ==========================================================
# MEMBER CHAT
# ==========================================================

@app.route("/member/chat", methods=["GET", "POST"])
def member_chat():

    # Member must be logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only members can access chat
    if session.get("role") != "member":
        return "Unauthorized", 403

    conn = None

    try:
        conn = get_connection()

        # --------------------------------------------------
        # SEND MESSAGE
        # --------------------------------------------------
        if request.method == "POST":

            message = request.form.get("message", "").strip()

            if message:

                user_id = session.get("user_id")
                user_name = session.get("name", "Member")

                with conn.cursor() as cur:

                    cur.execute("""
                        INSERT INTO member_messages
                        (
                            sender_id,
                            sender_name,
                            message
                        )
                        VALUES (%s, %s, %s)
                    """, (
                        user_id,
                        user_name,
                        message
                    ))

                conn.commit()

                return redirect(url_for("member_chat"))

        # --------------------------------------------------
        # GET MESSAGES
        # --------------------------------------------------

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    sender_id,
                    sender_name,
                    message,
                    created_at
                FROM member_messages
                ORDER BY created_at ASC
            """)

            messages = cur.fetchall()

        return render_template(
            "member_chat.html",
            messages=messages
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print("MEMBER CHAT ERROR:", e)

        return "Member chat error: " + str(e)

    finally:

        if conn:
            conn.close()
# ==========================================================
# RUN APPLICATION
# ==========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )