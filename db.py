import sqlite3
from datetime import datetime, timedelta

# DB 연결
conn = sqlite3.connect("princess.db", check_same_thread=False)
cursor = conn.cursor()

# 유저 정보 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    nickname TEXT,
    exp INTEGER DEFAULT 0
)
""")

# 출석 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id TEXT,
    date TEXT
)
""")

# 기상 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS wakeup (
    user_id TEXT,
    date TEXT
)
""")

# 공부 시간 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS study (
    user_id TEXT,
    date TEXT,
    minutes INTEGER
)
""")
conn.commit()


def _register_user(user_id, nickname):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id, ))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, nickname, exp) VALUES (?, ?, 0)",
            (user_id, nickname))


def save_attendance(user_id, nickname):
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT * FROM attendance WHERE user_id=? AND date=?",
                   (user_id, today))
    if cursor.fetchone():
        return False
    cursor.execute("INSERT INTO attendance (user_id, date) VALUES (?, ?)",
                   (user_id, today))
    _register_user(user_id, nickname)
    conn.commit()
    return True


def get_attendance(user_id):
    cursor.execute(
        "SELECT date FROM attendance WHERE user_id=? ORDER BY date DESC",
        (user_id, ))
    return cursor.fetchall()


def save_wakeup(user_id, nickname):
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT * FROM wakeup WHERE user_id=? AND date=?",
                   (user_id, today))
    if cursor.fetchone():
        return False
    cursor.execute("INSERT INTO wakeup (user_id, date) VALUES (?, ?)",
                   (user_id, today))
    _register_user(user_id, nickname)
    conn.commit()
    return True


def log_study_time(user_id, minutes):
    today = datetime.now().strftime("%Y-%m-%d")
    _register_user(user_id, "Unknown")  # 자동 등록 보장
    cursor.execute("SELECT minutes FROM study WHERE user_id=? AND date=?",
                   (user_id, today))
    row = cursor.fetchone()
    if row:
        total = row[0] + minutes
        cursor.execute("UPDATE study SET minutes=? WHERE user_id=? AND date=?",
                       (total, user_id, today))
    else:
        cursor.execute(
            "INSERT INTO study (user_id, date, minutes) VALUES (?, ?, ?)",
            (user_id, today, minutes))
    conn.commit()


def get_today_study_time(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT minutes FROM study WHERE user_id=? AND date=?",
                   (user_id, today))
    row = cursor.fetchone()
    return row[0] if row else 0


def add_exp(user_id, amount):
    cursor.execute("SELECT exp FROM users WHERE user_id=?", (user_id, ))
    row = cursor.fetchone()
    if row:
        new_exp = row[0] + amount
        cursor.execute("UPDATE users SET exp=? WHERE user_id=?",
                       (new_exp, user_id))
    else:
        cursor.execute(
            "INSERT INTO users (user_id, nickname, exp) VALUES (?, ?, ?)",
            (user_id, "Unknown", amount))
    conn.commit()


def get_level(user_id):
    cursor.execute("SELECT exp FROM users WHERE user_id=?", (user_id, ))
    row = cursor.fetchone()
    if not row:
        return 1
    exp = row[0]
    thresholds = [0, 30, 80, 150, 250, 400, 600, 900, 1300]
    level = 1
    for i, threshold in enumerate(thresholds):
        if exp < threshold:
            break
        level = i + 1
    return level


def get_top_users_by_exp(limit=10):
    cursor.execute(
        """
        SELECT nickname, exp FROM users
        ORDER BY exp DESC
        LIMIT ?
    """, (limit, ))
    return cursor.fetchall()


# ==============================
# 추가: 월/주별 통계 함수
# ==============================


def get_monthly_stats(user_id):
    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(
        day=1)  # 다음 달 1일
    month_end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

    # 출석
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM attendance
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, month_start, month_end))
    attendance = cursor.fetchone()[0]

    # 기상
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM wakeup
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, month_start, month_end))
    wakeup = cursor.fetchone()[0]

    # 공부일수 (하루 10분 이상)
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM study
        WHERE user_id=? AND date BETWEEN ? AND ? AND minutes >= 10
    """, (user_id, month_start, month_end))
    study_days = cursor.fetchone()[0]

    # 총 공부시간
    cursor.execute(
        """
        SELECT COALESCE(SUM(minutes), 0) FROM study
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, month_start, month_end))
    study_minutes = cursor.fetchone()[0]

    # 획득 경험치
    cursor.execute("""
        SELECT exp FROM users WHERE user_id=?
    """, (user_id, ))
    row = cursor.fetchone()
    exp = row[0] if row else 0

    return {
        "attendance": attendance,
        "wakeup": wakeup,
        "study_days": study_days,
        "study_minutes": study_minutes,
        "exp": exp
    }


def get_weekly_stats(user_id):
    now = datetime.now()
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    week_end = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")

    # 출석
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM attendance
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, week_start, week_end))
    attendance = cursor.fetchone()[0]

    # 기상
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM wakeup
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, week_start, week_end))
    wakeup = cursor.fetchone()[0]

    # 공부일수 (하루 10분 이상)
    cursor.execute(
        """
        SELECT COUNT(DISTINCT date) FROM study
        WHERE user_id=? AND date BETWEEN ? AND ? AND minutes >= 10
    """, (user_id, week_start, week_end))
    study_days = cursor.fetchone()[0]

    # 총 공부시간
    cursor.execute(
        """
        SELECT COALESCE(SUM(minutes), 0) FROM study
        WHERE user_id=? AND date BETWEEN ? AND ?
    """, (user_id, week_start, week_end))
    study_minutes = cursor.fetchone()[0]

    # 획득 경험치
    cursor.execute("""
        SELECT exp FROM users WHERE user_id=?
    """, (user_id, ))
    row = cursor.fetchone()
    exp = row[0] if row else 0

    return {
        "attendance": attendance,
        "wakeup": wakeup,
        "study_days": study_days,
        "study_minutes": study_minutes,
        "exp": exp
    }


# ==============================
# 연속 출석/기상/공부일수 함수
# ==============================


def get_streak_attendance(user_id):
    return _get_streak_days("attendance", user_id)


def get_streak_wakeup(user_id):
    return _get_streak_days("wakeup", user_id)


def get_streak_study(user_id):
    # 10분 이상 공부한 날만 streak로 인정
    cursor.execute(
        """
        SELECT date FROM study
        WHERE user_id=? AND minutes >= 10
        ORDER BY date DESC
    """, (user_id, ))
    rows = [row[0] for row in cursor.fetchall()]
    return _calculate_streak_from_dates(rows)


def _get_streak_days(table, user_id):
    cursor.execute(
        f"""
        SELECT date FROM {table}
        WHERE user_id=?
        ORDER BY date DESC
    """, (user_id, ))
    rows = [row[0] for row in cursor.fetchall()]
    return _calculate_streak_from_dates(rows)


def _calculate_streak_from_dates(date_list):
    if not date_list:
        return 0
    streak = 0
    today = datetime.now().date()
    for d in date_list:
        d_date = datetime.strptime(d, "%Y-%m-%d").date()
        if (today - d_date).days == streak:
            streak += 1
        else:
            break
    return streak
