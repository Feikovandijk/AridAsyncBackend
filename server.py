from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading
from datetime import datetime
from models import SessionLocal, AreaDeathCount, DreadLevel, PlayerNote, create_db_and_tables
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import contextlib
from functools import wraps  # For decorator
import os  # For environment variables
import json  # For parsing API keys from env
from dotenv import load_dotenv  # For .env file

load_dotenv()  # Load variables from .env file first

app = Flask(__name__)
CORS(app)

# --- API Key Authentication (from .env file) ---
VALID_API_KEYS_JSON = os.environ.get('VALID_API_KEYS_JSON')
VALID_API_KEYS = {}  # Default to empty if not set or invalid

print(f"[DEBUG] Initial VALID_API_KEYS_JSON from env: '{'present' if VALID_API_KEYS_JSON else 'not present'}'")

if VALID_API_KEYS_JSON:
    try:
        VALID_API_KEYS = json.loads(VALID_API_KEYS_JSON)
        if not isinstance(VALID_API_KEYS, dict):
            print(
                "Error: VALID_API_KEYS_JSON in .env did not parse into a dictionary. "
                "API key auth might not work as expected."
            )
            VALID_API_KEYS = {}  # Reset if not a dict
    except json.JSONDecodeError:
        print(
            "Error: VALID_API_KEYS_JSON in .env is not valid JSON. "
            "API key auth might not work as expected."
        )
        VALID_API_KEYS = {}  # Reset if not valid JSON

print(f"[DEBUG] Parsed VALID_API_KEYS: {{len(VALID_API_KEYS)}} keys loaded.")

if not VALID_API_KEYS:
    # For security, if keys are expected, the system should be restrictive.
    print(
        "CRITICAL WARNING: VALID_API_KEYS is not configured or is invalid. "
        "API key authentication will DENY ALL requests to protected routes."
    )  
    


def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # --- Rate Limiting Logic ---
        client_ip = request.remote_addr
        current_time = time.time()

        # Clean up old attempts for this IP
        if client_ip in request_attempts_by_ip:
            request_attempts_by_ip[client_ip] = [
                timestamp for timestamp in request_attempts_by_ip[client_ip]
                if current_time - timestamp < RATE_LIMIT_WINDOW_SECONDS
            ]
        else:
            request_attempts_by_ip[client_ip] = []

        # Check if rate limit exceeded
        if len(request_attempts_by_ip[client_ip]) >= RATE_LIMIT_ATTEMPTS:
            print(f"Rate limit exceeded for IP: {client_ip}")
            # Optionally, add a delay before responding to further deter attackers
            # time.sleep(1) # Example: 1 second delay
            return jsonify({"error": "Too Many Requests - Rate limit exceeded"}), 429

        # --- Original API Key Logic --- 
        if not VALID_API_KEYS:  # If keys are not loaded (e.g. misconfigured .env)
            print("API Key system not configured properly. Denying access.")
            return jsonify({"error": "API Key system configuration error"}), 500

        api_key = request.headers.get('X-API-KEY')

        # Record the attempt *before* checking the key
        # This ensures failed attempts are also counted towards the rate limit.
        request_attempts_by_ip[client_ip].append(current_time)

        if api_key and api_key in VALID_API_KEYS:
            # Optionally log which client is accessing:
            # print(f"API access by {VALID_API_KEYS[api_key]} using key ending with {api_key[-4:]}") # Example: log last 4 chars
            return f(*args, **kwargs)  # API key is valid, proceed
        else:
            print(f"Unauthorized API access attempt. Provided Key length: {len(api_key) if api_key else 0} for IP: {client_ip}")
            # No need to add to request_attempts_by_ip here again, as it was added before the check.
            return jsonify({"error": "Unauthorized - Invalid or missing API Key"}), 401
    return decorated_function

# --- DATABASE SETUP ---


# Helper to get a DB session and ensure it's closed
@contextlib.contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()  # Rollback in case of any exception during the session usage
        raise
    finally:
        db.close()


# --- CONFIGURATION ---
DEATH_COUNT_DECAY_FACTOR = 0.95
DECAY_INTERVAL_SECONDS = 3600
DREAD_CALCULATION_INTERVAL_SECONDS = 10
MIN_DEATHS_FOR_DREAD = 1

# --- RATE LIMITING CONFIGURATION ---
RATE_LIMIT_ATTEMPTS = 10  # Max # of attempts
RATE_LIMIT_WINDOW_SECONDS = 60  # Per # of seconds
request_attempts_by_ip = {} # Stores IP: [timestamps]


# --- DREAD CALCULATION LOGIC ---
def calculate_and_assign_dread_levels():
    with get_db() as db:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Calculating dread levels...")
        try:
            death_counts_query = db.query(AreaDeathCount).all()
            if not death_counts_query:
                print("No death data to process. Resetting all dread levels.")
                db.query(DreadLevel).update({DreadLevel.level: 0})
                db.commit()
                return

            eligible_areas = [
                (area.area_id, area.death_count)
                for area in death_counts_query
                if area.death_count >= MIN_DEATHS_FOR_DREAD
            ]

            if not eligible_areas:
                print("No areas eligible for dread levels. Resetting all dread levels.")
                db.query(DreadLevel).update({DreadLevel.level: 0})
                db.commit()
                return

            sorted_areas_by_deaths = sorted(eligible_areas, key=lambda x: x[1], reverse=True)

            db.query(DreadLevel).update({DreadLevel.level: 0})

            if len(sorted_areas_by_deaths) > 0:
                top_area_id, count = sorted_areas_by_deaths[0]
                update_or_create_dread_level(db, top_area_id, 2)
                print(f"  Assigning Dread Level 2 to: {top_area_id} (Deaths: {count})")

            if len(sorted_areas_by_deaths) > 1:
                second_area_id, count = sorted_areas_by_deaths[1]
                update_or_create_dread_level(db, second_area_id, 1)
                print(f"  Assigning Dread Level 1 to: {second_area_id} (Deaths: {count})")

            db.commit()
            print("Dread levels updated in database")
        except IntegrityError as e:
            print(f"Database integrity error during dread calculation: {e}")
            db.rollback()
        except Exception as e:
            print(f"Error during dread calculation: {e}")
            db.rollback()
            raise


def update_or_create_dread_level(db: Session, area_id: str, level: int):
    dread_level = db.query(DreadLevel).filter_by(area_id=area_id).first()
    if dread_level:
        dread_level.level = level
        dread_level.last_updated = datetime.utcnow()
    else:
        db.add(DreadLevel(area_id=area_id, level=level))
    # Commit will be handled by the calling function (calculate_and_assign_dread_levels)


def decay_death_counts():
    with get_db() as db:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Applying decay to death counts...")
        try:
            death_counts_query = db.query(AreaDeathCount).all()
            if not death_counts_query:
                print("No death counts to decay.")
                return

            for death_count_obj in death_counts_query:  # Renamed to avoid conflict
                death_count_obj.death_count = round(death_count_obj.death_count * DEATH_COUNT_DECAY_FACTOR)
                if death_count_obj.death_count < 1:
                    db.delete(death_count_obj)
                    print(f"  Removed {death_count_obj.area_id} from death_counts due to low count after decay.")
                else:
                    death_count_obj.last_updated = datetime.utcnow()

            db.commit()
            print("Death counts decayed in database")
        except IntegrityError as e:
            print(f"Database integrity error during death count decay: {e}")
            db.rollback()
        except Exception as e:
            print(f"Error during death count decay: {e}")
            db.rollback()
            raise


# --- API ENDPOINTS ---

@app.route('/api/log_death', methods=['POST'])
@require_api_key  # Protect this route
def log_death():
    data = request.get_json()
    area_id = data.get('area_id')
    if not area_id:
        return jsonify({"error": "area_id is required"}), 400

    with get_db() as db:
        try:
            death_count = db.query(AreaDeathCount).filter_by(area_id=area_id).first()
            if death_count:
                death_count.death_count += 1
                death_count.last_updated = datetime.utcnow()
            else:
                death_count = AreaDeathCount(area_id=area_id, death_count=1)
                db.add(death_count)

            db.commit()
            current_deaths = death_count.death_count  # Get after potential creation/update
            client_name = VALID_API_KEYS.get(request.headers.get('X-API-KEY'), "Unknown Client")
            # Log client name (which is a description from your .env, not the key itself)
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Death logged in: {area_id}. "
                f"Total deaths: {current_deaths} by {client_name}"
            )
            return jsonify({"message": f"Death logged for {area_id}", "current_deaths_in_area": current_deaths}), 200
        except IntegrityError as e:
            db.rollback()
            print(f"Database integrity error logging death: {e}")
            # Check if it's a unique constraint on area_id, which shouldn't happen with current logic
            # but good to be aware of. The primary key ID constraint is more likely here if IDs are mishandled.
            return jsonify({"error": "Database error: Could not log death due to data conflict."}), 500
        except Exception as e:
            db.rollback()
            print(f"Error logging death: {e}")
            return jsonify({"error": "An unexpected error occurred."}), 500


@app.route('/api/get_dread_level', methods=['GET'])
# Not protecting GET for simplicity, can be added if needed by uncommenting:
# @require_api_key
def get_dread_level():
    area_id = request.args.get('area_id')
    if not area_id:
        return jsonify({"error": "area_id is required"}), 400

    with get_db() as db:
        dread_level_obj = db.query(DreadLevel).filter_by(area_id=area_id).first()
        level = dread_level_obj.level if dread_level_obj else 0

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Specific dread level requested for {area_id}. Sending: {level}")
    return jsonify({"area_id": area_id, "dread_level": level}), 200


@app.route('/api/get_elevated_dread_areas', methods=['GET'])
# @require_api_key
def get_elevated_dread_areas():
    with get_db() as db:
        elevated_areas_query = db.query(DreadLevel).filter(DreadLevel.level > 0).all()

    result = [
        {"area_id": area.area_id, "dread_level": area.level}
        for area in sorted(elevated_areas_query, key=lambda x: x.level, reverse=True)
    ]

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Elevated dread areas requested. Sending: {result}")
    return jsonify(result), 200


""" # --- Notes System ---
PRE_DEFINED_WORDS = ["danger", "safe", "hidden", "treasure", "monster", "trap", "forward", "back", "help"]


@app.route('/api/leave_note', methods=['POST'])
@require_api_key  # Protect this route
def leave_note():
    data = request.get_json()
    area_id = data.get('area_id')
    note_location_id = data.get('note_location_id')
    word = data.get('word')

    if not all([area_id, note_location_id, word]):
        return jsonify({"error": "area_id, note_location_id, and word are required"}), 400
    if word not in PRE_DEFINED_WORDS:
        return jsonify({"error": f"Invalid word. Choose from: {PRE_DEFINED_WORDS}"}), 400

    with get_db() as db:
        try:
            # The UniqueConstraint in PlayerNote model with sqlite_on_conflict='REPLACE' handles overwriting.
            note = PlayerNote(
                area_id=area_id,
                note_location_id=note_location_id,
                word=word
            )
            db.add(note)  # add will become a merge/replace due to the constraint
            db.commit()

            client_name = VALID_API_KEYS.get(request.headers.get('X-API-KEY'), "Unknown Client")
            # Log client name (description from .env, not the key itself)
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Note left/updated at "
                f"{area_id}_{note_location_id}: {word} by {client_name}"
            )
            return jsonify({"message": "Note left/updated successfully"}), 200
        except IntegrityError as e:  # Should be less likely with REPLACE but good to have
            db.rollback()
            print(f"Database integrity error leaving note: {e}")
            return jsonify({"error": "Database error: Could not leave note due to data conflict."}), 500
        except Exception as e:
            db.rollback()
            print(f"Error leaving note: {e}")
            return jsonify({"error": "An unexpected error occurred."}), 500


@app.route('/api/get_player_notes', methods=['GET'])
# @require_api_key
def get_player_notes():
    area_id = request.args.get('area_id')
    if not area_id:
        return jsonify({"error": "area_id is required"}), 400

    with get_db() as db:
        notes_query = db.query(PlayerNote).filter_by(area_id=area_id).all()
    result = [{"location_id": note.note_location_id, "word": note.word} for note in notes_query]

    return jsonify(result), 200 """


# --- PERIODIC TASK SCHEDULER ---
def run_periodic_tasks():  # noqa: C901
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting periodic task scheduler...")
    # Initial calls outside the loop with their own sessions
    try:
        calculate_and_assign_dread_levels()
    except Exception as e:
        print(f"Error in initial dread calculation: {e}")
    try:
        decay_death_counts()  # Also call decay initially
    except Exception as e:
        print(f"Error in initial death count decay: {e}")

    last_decay_time = time.time()
    last_dread_calc_time = time.time()

    while True:
        # Use a short sleep to prevent tight looping if an error occurs immediately
        # and to serve as the main polling interval for the scheduler.
        time.sleep(5)

        current_time_for_checks = time.time() # Sample current time after sleeping

        try:
            # Check for decay interval first, as it also triggers dread calculation
            if current_time_for_checks - last_decay_time >= DECAY_INTERVAL_SECONDS:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Triggering decay_death_counts and "
                    f"calculate_and_assign_dread_levels due to decay interval..."
                )
                decay_death_counts()
                calculate_and_assign_dread_levels()
                last_decay_time = time.time()  # Update time after successful completion
                last_dread_calc_time = last_decay_time  # Reset dread calc time as it ran too
            # If decay didn't run, check for dread calculation interval
            elif current_time_for_checks - last_dread_calc_time >= DREAD_CALCULATION_INTERVAL_SECONDS:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Triggering calculate_and_assign_dread_levels "
                    f"due to dread calculation interval..."
                )
                calculate_and_assign_dread_levels()
                last_dread_calc_time = time.time()  # Update time after successful completion
        except Exception as e:
            # Log the error and continue the loop so the scheduler doesn't die
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXCEPTION in periodic task loop: {e}. "
                f"Attempting to continue..."
            )
            # Potentially add a longer sleep here if errors are persistent to avoid spamming logs
            # time.sleep(60) # e.g. wait a minute before retrying loop logic if error occurs

        # The complex conditional sleep block previously here (lines 352-361 of original)
        # has been removed. The time.sleep(5) at the top of the loop now solely dictates
        # the polling frequency of the scheduler.


if __name__ == '__main__':
    # Ensure the database and tables are created before starting
    print("Ensuring database and tables are created if they don't exist...")
    create_db_and_tables()  # Call the new function

    scheduler_thread = threading.Thread(target=run_periodic_tasks, daemon=True)
    scheduler_thread.start()
    print("Starting Flask server with periodic dread calculation task on host 0.0.0.0, port from FLASK_RUN_PORT or default 5001...")
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get("FLASK_RUN_PORT", 5001)))
