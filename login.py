import json
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__, template_folder=str(BASE_DIR))
app.secret_key = "change-this-secret-key"

DB_PATH = BASE_DIR / "database.db"

BUILD_COLUMNS = [
    "selected_mode",
    "selected_reaction",
    "selected_pressure_reaction",
    "stop_time",
    "distance",
    "motion_points_json",
    "voltage",
    "resistance",
    "torque_constant",
    "w_max",
    "mass",
    "wheel_mass",
    "number_wheels",
    "radius",
    "reaction_time",
    "volume",
    "pressure_w_no_load_default",
    "pressure_stall_torque_default",
    "default_pressure",
    "thiosulfate",
    "hydrogen_peroxide",
    "pressure_hydrogen_peroxide",
    "iodine",
    "peroxodisulfate",
    "ascorbicacid",
    "bisulfate",
    "iodate",
    "sodium_bicarbonate",
    "calcium_carbonate",
    "zinc",
    "carbon_dioxide",
    "bearing_friction",
    "rolling_friction",
    "g",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            selected_mode TEXT DEFAULT 'battery',
            selected_reaction TEXT DEFAULT 'time_stop_thiosulfate',
            selected_pressure_reaction TEXT DEFAULT 'pressure_release_dry_ice',
            stop_time REAL,
            distance REAL,
            motion_points_json TEXT,
            voltage REAL,
            resistance REAL,
            torque_constant REAL,
            w_max REAL,
            mass REAL,
            wheel_mass REAL,
            number_wheels INTEGER,
            radius REAL,
            reaction_time REAL,
            volume REAL,
            pressure_w_no_load_default REAL,
            pressure_stall_torque_default REAL,
            default_pressure REAL,
            thiosulfate REAL,
            hydrogen_peroxide REAL,
            pressure_hydrogen_peroxide REAL,
            iodine REAL,
            peroxodisulfate REAL,
            ascorbicacid REAL,
            bisulfate REAL,
            iodate REAL,
            sodium_bicarbonate REAL,
            calcium_carbonate REAL,
            zinc REAL,
            carbon_dioxide REAL,
            bearing_friction REAL,
            rolling_friction REAL,
            g REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(builds)").fetchall()
    }
    for name, column_type in {
        "stop_time": "REAL",
        "distance": "REAL",
        "motion_points_json": "TEXT",
    }.items():
        if name not in existing_columns:
            cursor.execute(f"ALTER TABLE builds ADD COLUMN {name} {column_type}")
    conn.commit()
    conn.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT id, username FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def build_payload_from_request():
    data = request.get_json(silent=True) or {}
    build = {name: data.get(name) for name in BUILD_COLUMNS}
    build["name"] = (data.get("name") or "Untitled Build").strip()
    return build


@app.route("/")
@app.route("/index.html")
def calculator_page():
    return render_template("index.html")


@app.route("/builds")
@app.route("/builds.html")
def builds_page():
    return render_template("builds.html")


@app.route("/api/me")
def api_me():
    return jsonify({"user": current_user()})


@app.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "That username is already taken."}), 409

    session["user_id"] = cursor.lastrowid
    conn.close()
    return jsonify({"user": current_user()})


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db()
    user = conn.execute(
        "SELECT id, username, password FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Incorrect username or password."}), 401

    session["user_id"] = user["id"]
    return jsonify({"user": {"id": user["id"], "username": user["username"]}})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"user": None})


@app.route("/api/builds", methods=["GET", "POST"])
def api_builds():
    user = current_user()
    if not user:
        return jsonify({"error": "Please sign up or log in first."}), 401

    conn = get_db()

    if request.method == "POST":
        build = build_payload_from_request()
        column_names = ["user_id", "name", *BUILD_COLUMNS]
        placeholders = ", ".join(["?"] * len(column_names))
        values = [user["id"], build["name"], *[build[name] for name in BUILD_COLUMNS]]
        conn.execute(
            f"INSERT INTO builds ({', '.join(column_names)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()

    rows = conn.execute(
        """
        SELECT *
        FROM builds
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()

    builds = []
    for row in rows:
        build = dict(row)
        build["data_json"] = json.dumps({name: build[name] for name in BUILD_COLUMNS})
        builds.append(build)

    return jsonify({"builds": builds})


@app.route("/api/builds/<int:build_id>", methods=["DELETE"])
def api_delete_build(build_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Please sign up or log in first."}), 401

    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM builds WHERE id = ? AND user_id = ?",
        (build_id, user["id"]),
    )
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "Build not found."}), 404

    return api_builds()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
