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
# DONATIONS
# ==========================================================

@app.route(
    "/donations",
    methods=["GET", "POST"]
)
@app.route(
    "/collect-donation",
    methods=["GET", "POST"]
)
def donations():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in [
        "admin",
        "member"
    ]:
        return redirect(url_for("login"))

    message = None
    error = None

    conn = None

    try:

        conn = get_connection()

        # --------------------------------------------------
        # ADD DONATION
        # --------------------------------------------------

        if request.method == "POST":

            donor_name = request.form.get(
                "donor_name",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            amount = request.form.get(
                "amount",
                ""
            ).strip()

            payment_method = request.form.get(
                "payment_method",
                "Cash"
            ).strip()

            payment_status = request.form.get(
                "payment_status",
                "Paid"
            ).strip()

            if not donor_name:

                error = "Donor name is required."

            elif not amount:

                error = "Donation amount is required."

            else:

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
                        VALUES
                        (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
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

                message = (
                    "Donation added successfully!"
                )

        # --------------------------------------------------
        # GET DONATIONS
        # --------------------------------------------------

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
                    u.name
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
            message=message,
            error=error
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "DONATION ERROR:",
            e
        )

        return (
            "Donation error: "
            + str(e)
        )

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