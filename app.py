import os
from datetime import datetime
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ── AUTH ──────────────────────────────────────────────────



# ── DATABASE ──────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_db():
    conn = psycopg.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_log (
            id SERIAL PRIMARY KEY,
            log_date TEXT NOT NULL UNIQUE,
            checks TEXT DEFAULT '{}',
            water INTEGER DEFAULT 0,
            mood TEXT DEFAULT '{}',
            xp_earned INTEGER DEFAULT 0,
            completion_pct INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("PostgreSQL database initialized")

# ── PROTOCOL ──────────────────────────────────────────────
PROTOCOL_VERSION = "1.7.0"
PROTOCOL_NOTES = "Added Recovery section: home red light sauna daily, bathhouse sauna + cold plunge 3x/week, contrast therapy protocol, TMS day red light timing"

SECTIONS = [
    {
        "id": "sleep",
        "icon": "🌙",
        "title": "Sleep Protocol",
        "color": "sleep",
        "xpEach": 3,
        "items": [
            {"id": "s1", "label": "In bed by 10:30 PM last night", "note": "Fixed anchor — same every night", "tag": "crit", "tagLabel": "Critical"},
            {"id": "s2", "label": "Woke at 9:00 AM — no snooze", "note": "Your committed anchor time · same 7 days a week including weekends · circadian dopamine reset for COMT Val/Val", "tag": "crit", "tagLabel": "Critical"},
            {"id": "s3", "label": "Within 30 min of waking: step outside for light", "note": "10 min outdoor light · no sunglasses · strongest circadian signal available · pairs with red light sauna", "tag": "key", "tagLabel": "Key"},
        ]
    },
    {
        "id": "morning",
        "icon": "🌄",
        "title": "Morning Routine",
        "color": "morning",
        "xpEach": 2,
        "items": [
            {"id": "m1", "label": "16 oz water immediately on waking (9:00 AM)", "note": "Before anything else · pinch of sea salt · rehydrates overnight · starts homocysteine clearance", "tag": "daily", "tagLabel": "Daily"},
            {"id": "m6", "label": "10 min outdoor light + red light sauna 15 min", "note": "COMT Val/Val: morning light + red light + movement is your most powerful dopamine stack. Red light sauna first (mitochondrial ATP, prefrontal support, circadian signal) then outdoor light. Both before walking/cycling.", "tag": "crit", "tagLabel": "9:05–9:20 AM"},
            {"id": "m7", "label": "Walking or cycling: 20–30 min moderate pace (Prospect Park, walk, or stationary bike)", "note": "Core daily feature — not optional. Moderate pace only. Walking or cycling within 2 hrs of TMS amplifies neuroplasticity. Raises prefrontal dopamine for COMT Val/Val. Lowers homocysteine. Improves HDL.", "tag": "crit", "tagLabel": "9:20–9:50 AM"},
            {"id": "m2", "label": "Breakfast — 2 eggs + greens + berries", "note": "After cycling · eggs (choline) · spinach/arugula (natural folate) · blueberries (anti-neuroinflammation) · eat within 45 min of finishing walk or ride", "tag": "key", "tagLabel": "~10:00 AM"},
            {"id": "m3", "label": "Morning supplements taken with breakfast", "note": "Enlyte · D3/K2 · Fish oil — with food · D3 and fish oil require fat to absorb", "tag": "crit", "tagLabel": "Critical"},
            {"id": "m8", "label": "1 cup filtered drip coffee with or after breakfast", "note": "Filtered only (not French press/espresso — diterpenes raise homocysteine) · with food not empty stomach · CYP1A2 boosted by smoking = harder crash · 1 cup max · STOP by 10:30 AM", "tag": "key", "tagLabel": "~10:00 AM"},
            {"id": "m4", "label": "Green tea Cup 1 — 45–60 min AFTER Enlyte (~11:00 AM)", "note": "Wait 45-60 min after Enlyte — tannins reduce methylfolate absorption · brew at 170F 1-2 min · Japanese sencha preferred · L-theanine + caffeine = calm focus without anxiety spike", "tag": "key", "tagLabel": "~11:00 AM"},
        ]
    },
    {
        "id": "supplements",
        "icon": "💊",
        "title": "Supplements",
        "color": "supplements",
        "xpEach": 4,
        "items": [
            {"id": "sup1", "label": "Enlyte — 1 capsule with breakfast", "note": "L-methylfolate 7mg + folinic acid 3.5mg + adenosylcobalamin B12 50mcg + P5P trace · adenosylcobalamin is the mitochondrial B12 form (not methylcobalamin) — both are active, both superior to cyanocobalamin · most critical intervention for MTHFR C677T homozygous", "tag": "crit", "tagLabel": "Critical"},
            {"id": "sup2", "label": "Vitamin D3 5,000 IU + K2 100mcg with breakfast", "note": "Take with fat · was insufficient in 2020 labs · target 50-70 ng/mL", "tag": "crit", "tagLabel": "Critical"},
            {"id": "sup3", "label": "Fish oil 2–3g EPA with largest meal", "note": "EPA:DHA ratio favoring EPA · raises HDL · antidepressant evidence for COMT Val/Val", "tag": "key", "tagLabel": "Key"},
            {"id": "sup4", "label": "Vitamin E 400 IU (mixed tocopherols) with dinner", "note": "Was deficient in 2020 labs · take with fat · mixed not alpha-only", "tag": "daily", "tagLabel": "Daily"},
            {"id": "sup5", "label": "Magnesium glycinate 300–400mg at 9:45 PM", "note": "Glycinate form only · GABA support · lowers cortisol · supports methylation · START HERE before melatonin", "tag": "crit", "tagLabel": "9:45 PM"},
            {"id": "sup6", "label": "Melatonin 0.3–0.5mg at 9:00 PM — Phase 2 only", "note": "Start ONLY after 2-3 weeks on magnesium. 0.3-0.5mg ONLY — no gummies (testosterone risk at 5-10mg). COMT report recommends for homocysteine. Pure Encapsulations 0.5mg or Life Extension 0.3mg.", "tag": "phase2", "tagLabel": "Phase 2"},
            {"id": "sup7", "label": "Guanfacine 4mg as prescribed", "note": "As prescribed — works synergistically with TMS for prefrontal function", "tag": "rx", "tagLabel": "Rx"},
            {"id": "sup8", "label": "No synthetic folic acid today", "note": "No fortified cereal, enriched bread, folic acid supplements — competes with Enlyte methylfolate receptors", "tag": "avoid", "tagLabel": "Avoid"},
        ]
    },
    {
        "id": "meals",
        "icon": "🥗",
        "title": "Meals",
        "color": "meals",
        "xpEach": 2,
        "items": [
            {"id": "f1", "label": "Breakfast: 2 whole eggs (not just whites)", "note": "Choline source — supports methylation pathway directly", "tag": "crit", "tagLabel": "Must", "dividerBefore": "Breakfast ~10:00 AM"},
            {"id": "f2", "label": "Breakfast: Large handful dark leafy greens", "note": "Natural food folate — sauté with eggs or raw", "tag": "key", "tagLabel": "Key"},
            {"id": "f3", "label": "Breakfast: Half cup berries (blueberries preferred)", "note": "Anthocyanins reduce neuroinflammation · low glycemic · prefrontal cortex support", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f4", "label": "Lunch: Large salad with protein", "note": "Lentils/chickpeas/chicken/turkey/salmon · tyrosine for dopamine synthesis — essential for COMT Val/Val", "tag": "crit", "tagLabel": "Must", "dividerBefore": "Lunch ~1:00 PM"},
            {"id": "f5", "label": "Lunch: Olive oil dressing + pumpkin seeds", "note": "Pumpkin seeds: zinc + magnesium + tyrosine · olive oil supports HDL", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f6", "label": "Green tea Cup 2 — 60 min after lunch (~2:30 PM)", "note": "Midday focus lift · L-theanine prevents anxiety spike · LAST caffeine of day · no caffeine after 2:30 PM", "tag": "key", "tagLabel": "~2:30 PM"},
            {"id": "f7", "label": "Dinner: Fatty fish or turkey", "note": "3-4x per week fatty fish (salmon/mackerel/sardines) · EPA/DHA raises HDL · amplifies TMS response", "tag": "crit", "tagLabel": "Priority", "dividerBefore": "Dinner 7:00–7:30 PM"},
            {"id": "f8", "label": "Dinner: Beets or asparagus as side", "note": "Beets: betaine directly bypasses MTHFR — lowers homocysteine. Asparagus: highest food folate.", "tag": "key", "tagLabel": "Key"},
            {"id": "f9", "label": "Dinner: Cooked vegetable in olive oil only", "note": "No seed oils (canola/soybean/corn) — olive oil or butter only", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f10", "label": "Snack: Walnuts (small handful) midday", "note": "Plant omega-3s · melatonin precursors · COMT Val/Val cognitive support per genetic report", "tag": "daily", "tagLabel": "Daily", "dividerBefore": "Snacks"},
            {"id": "f11", "label": "Snack: Plain full-fat yogurt OR kefir — never flavored", "note": "Kefir preferred — broadest probiotic profile · gut-brain axis · tyrosine for dopamine · B12 · NO flavored varieties (15-25g sugar negates all benefit)", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f14", "label": "Fruit: whole fruit only — no juice", "note": "Whole fruit OK daily (fiber intact) · berries preferred · NO commercial juice: concentrated sugar, often folic-acid fortified, zero fiber · Lemon/lime squeeze on food is fine", "tag": "key", "tagLabel": "Key"},
            {"id": "f15", "label": "Full-fat dairy always over low-fat", "note": "Fat-soluble vitamins D3/E/K2 need dietary fat to absorb · full-fat supports HDL · hard aged cheese fine in moderation — high tyrosine + B12 + zinc", "tag": "daily", "tagLabel": "Daily", "dividerBefore": "Dairy Guide"},
            {"id": "f12", "label": "Avoided: fortified cereal, white bread, enriched pasta", "note": "Synthetic folic acid competes with Enlyte methylfolate receptors — critical for MTHFR C677T homozygous", "tag": "avoid", "tagLabel": "Avoid", "dividerBefore": "Avoid Today"},
            {"id": "f13", "label": "Avoided: commercial fruit juice, sugary drinks, soda", "note": "Juice: blood sugar spike + often folic-acid fortified + zero fiber · Blood sugar instability directly worsens OCD and anxiety", "tag": "avoid", "tagLabel": "Avoid"},
            {"id": "f16", "label": "Avoided: flavored yogurt (Chobani fruit, Yoplait, etc.)", "note": "15-25g added sugar per serving negates all probiotic benefit · same glucose spike as juice · plain only", "tag": "avoid", "tagLabel": "Avoid"},
            {"id": "f17", "label": "Avoided: processed cheese (American slices, Velveeta)", "note": "Heavily processed · additives · high sodium · use real aged cheese instead", "tag": "avoid", "tagLabel": "Avoid"},
        ]
    },
    {
        "id": "hydration",
        "icon": "💧",
        "title": "Hydration",
        "color": "hydration",
        "xpEach": 2,
        "items": [
            {"id": "h1", "label": "8+ cups water today (track with water counter)", "note": "Primary hydration — essential for B vitamin absorption and kidney filtration of homocysteine", "tag": "daily", "tagLabel": "Daily", "water": True},
            {"id": "h5", "label": "Coconut water: post-exercise or post-sauna only — 1 cup max", "note": "Good electrolytes (potassium/magnesium) · better than sports drinks · BUT 9-11g sugar per cup means NOT for all-day hydration · glucose has been volatile in your labs · use water + ConcenTrace or LMNT for daily hydration", "tag": "key", "tagLabel": "Post-exercise"},
            {"id": "h2", "label": "Coffee window closed — had 1 cup this morning (no more after 10:30 AM)", "note": "Coffee is a structured morning item · filtered drip only · no second cup · CYP1A2 from smoking means caffeine crashes harder than average", "tag": "key", "tagLabel": "Reminder"},
            {"id": "h3", "label": "No caffeine after 2:30 PM", "note": "5-7 hr half-life means afternoon caffeine disrupts your 10:30 PM bedtime · hard stop", "tag": "crit", "tagLabel": "Hard stop"},
            {"id": "h4", "label": "No alcohol today", "note": "Alcohol is a potent folate antagonist and homocysteine raiser — zero tolerance", "tag": "avoid", "tagLabel": "Non-negotiable"},
        ]
    },
    {
        "id": "exercise",
        "icon": "🏃",
        "title": "Movement & Exercise",
        "color": "exercise",
        "xpEach": 5,
        "items": [
            {"id": "e1", "label": "Morning walk or cycling DONE (logged in morning routine above)", "note": "Core daily walk or ride in morning block 9:20-9:50 AM · check here to confirm · walking counts fully · if missed: do it now before 2 PM — still within TMS amplification window", "tag": "crit", "tagLabel": "Core"},
            {"id": "e5", "label": "Resistance training 20–30 min (Tue/Thu)", "note": "Bodyweight: squats/pushups/lunges/planks · raises BDNF · amplifies TMS · do AFTER cycling · antidepressant evidence comparable to SSRIs", "tag": "key", "tagLabel": "Tue/Thu"},
            {"id": "e6", "label": "Second short walk or cycle 15–20 min (afternoon — optional)", "note": "Optional but powerful on TMS days — BDNF peaks again 90-120 min after second session · keep moderate pace", "tag": "daily", "tagLabel": "Optional"},
            {"id": "e2", "label": "Yoga or stretching 30 min (Saturday)", "note": "Yoga Nidra or restorative yoga · activates parasympathetic system · counters OCD hypervigilance · lowers cortisol · Yoga with Adriene on YouTube free", "tag": "daily", "tagLabel": "Saturday"},
            {"id": "e4", "label": "Did not smoke more than yesterday", "note": "Each cigarette depletes folate + Vitamin C · raises homocysteine · reduces Enlyte effectiveness · goal: reduce 1 per week toward zero", "tag": "crit", "tagLabel": "Reduce"},
        ]
    },
    {
        "id": "tms",
        "icon": "🧠",
        "title": "TMS & Treatment",
        "color": "tms",
        "xpEach": 4,
        "items": [
            {"id": "t1", "label": "TMS session attended (if scheduled today)", "note": "Take supplements before session · methylfolate supports neurotransmitter substrate · cycling within 2 hrs amplifies neuroplasticity · no THC on TMS days", "tag": "crit", "tagLabel": "Priority"},
            {"id": "t2", "label": "Post-TMS: 20 min rest or gentle walk", "note": "Allow neuroplasticity window to consolidate · avoid stressful stimuli 30 min after · no THC (reduces cortical excitability TMS is trying to enhance)", "tag": "key", "tagLabel": "Key"},
            {"id": "t3", "label": "Guanfacine taken as prescribed", "note": "Rx compliance critical — works synergistically with TMS for prefrontal function", "tag": "rx", "tagLabel": "Rx"},
            {"id": "t4", "label": "Therapy / ERP session (if scheduled)", "note": "Exposure and Response Prevention is gold standard for OCD alongside TMS and pharmacological support", "tag": "key", "tagLabel": "Key"},
        ]
    },
    {
        "id": "recovery",
        "icon": "🔥",
        "title": "Recovery & Optimization",
        "color": "recovery",
        "xpEach": 4,
        "items": [
            {"id": "rec1", "label": "Red light sauna — home unit (daily)", "note": "20 min · red/NIR boosts mitochondrial ATP for methylation · prefrontal oxygenation · antidepressant serotonin mechanism · photobiomodulation is the key home advantage · not within 2 hrs of bedtime", "tag": "crit", "tagLabel": "Daily"},
            {"id": "rec2", "label": "Bathhouse: hot sauna + cold plunge (3x this week)", "note": "Hotter sauna (90-100C) = stronger dopamine and norepinephrine than home unit · cold plunge after: dopamine +300% sustained 2-3 hrs · 2-3 rounds contrast therapy = most powerful non-pharma dopamine protocol for COMT Val/Val · suggested Mon/Wed/Fri", "tag": "key", "tagLabel": "3x/week"},
            {"id": "rec3", "label": "Cold shower — daily minimum on home days", "note": "End morning shower with 60-90 sec cold water · real dopamine and norepinephrine response · pairs with cycling and red light for full morning dopamine stack · enter slowly — guanfacine lowers BP, cold spikes it briefly", "tag": "daily", "tagLabel": "Daily"},
            {"id": "rec4", "label": "Red light before TMS (if TMS scheduled today)", "note": "10-15 min NIR on forehead/scalp before session · mitochondrial energy support for prefrontal neurons TMS will stimulate · complementary mechanisms — zero interference · leave 60-90 min between sauna and TMS for core temp to normalize", "tag": "key", "tagLabel": "TMS days"},
            {"id": "rec5", "label": "Sauna finished before 7:30 PM (not within 2 hrs of bed)", "note": "Core temp must drop to initiate melatonin onset · sauna too close to bed disrupts your sleep anchor · schedule home sauna before 7:30 PM for evening sessions", "tag": "crit", "tagLabel": "Timing"},
            {"id": "rec6", "label": "Post-sauna: water + electrolytes immediately after every session", "note": "Significant fluid loss every session · 16-24 oz water with ConcenTrace or LMNT · correct moment for coconut water (1 cup) — post-sauna electrolyte replacement is its legitimate use", "tag": "daily", "tagLabel": "Always"},
        ]
    },
    {
        "id": "evening",
        "icon": "🌆",
        "title": "Evening Routine",
        "color": "evening",
        "xpEach": 3,
        "items": [
            {"id": "ev1", "label": "Dinner complete by 7:30 PM", "note": "3 hr gap before bed · eating late disrupts sleep architecture and cortisol rhythm", "tag": "key", "tagLabel": "Key"},
            {"id": "ev2", "label": "Vitamin E 400 IU taken with dinner", "note": "With fat — was deficient in 2020 labs · mixed tocopherols form", "tag": "daily", "tagLabel": "Daily"},
            {"id": "ev3", "label": "9:00 PM — Melatonin 0.3–0.5mg (Phase 2 only)", "note": "Circadian signal not sedative · 90 min before bed · start after 2-3 wks on magnesium · 0.3-0.5mg ONLY — no gummies · COMT report supports for homocysteine", "tag": "phase2", "tagLabel": "Phase 2"},
            {"id": "ev4", "label": "9:45 PM — Magnesium glycinate 300–400mg", "note": "GABA activity · lowers nocturnal cortisol · supports methylation · start here BEFORE adding melatonin", "tag": "crit", "tagLabel": "Critical"},
            {"id": "ev5", "label": "Screens off / night mode by 10:00 PM", "note": "Blue light suppresses endogenous melatonin · critical for sleep quality and dopamine baseline tomorrow", "tag": "key", "tagLabel": "Key"},
            {"id": "ev6", "label": "In bed by 10:30 PM", "note": "Non-negotiable — irregular sleep raises homocysteine and undermines TMS neuroplasticity consolidation", "tag": "crit", "tagLabel": "Fixed"},
        ]
    },
]

MOOD_KEYS = ['mood', 'anxiety', 'energy', 'sleep_quality']

LEVELS = [
    {"level": 1, "title": "Beginning", "xpRequired": 0},
    {"level": 2, "title": "Awakening", "xpRequired": 100},
    {"level": 3, "title": "Consistent", "xpRequired": 250},
    {"level": 4, "title": "Building", "xpRequired": 450},
    {"level": 5, "title": "Committed", "xpRequired": 700},
    {"level": 6, "title": "Disciplined", "xpRequired": 1000},
    {"level": 7, "title": "Thriving", "xpRequired": 1400},
    {"level": 8, "title": "Strong", "xpRequired": 1900},
    {"level": 9, "title": "Resilient", "xpRequired": 2500},
    {"level": 10, "title": "Flourishing", "xpRequired": 3200},
    {"level": 11, "title": "Mastery", "xpRequired": 4000},
    {"level": 12, "title": "Protocol Master", "xpRequired": 5000},
]

# ── API ROUTES ────────────────────────────────────────────

# Initialize DB on startup
try:
    init_db()
except Exception as e:
    print("DB init warning:", e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/protocol', methods=['GET'])
def get_protocol():
    return jsonify({
        "version": PROTOCOL_VERSION,
        "notes": PROTOCOL_NOTES,
        "sections": SECTIONS,
        "levels": LEVELS,
        "moodKeys": MOOD_KEYS,
    })

@app.route('/api/today', methods=['GET'])
def get_today():
    today = date.today().isoformat()
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM daily_log WHERE log_date = %s', (today,))
        row = c.fetchone()
        conn.close()
        if row:
            return jsonify({
                "date": row['log_date'],
                "checks": json.loads(row['checks'] or '{}'),
                "water": row['water'],
                "mood": json.loads(row['mood'] or '{}'),
                "xp_earned": row['xp_earned'],
                "completion_pct": row['completion_pct'],
            })
    except Exception as e:
        print("DB error:", e)
    return jsonify({"date": today, "checks": {}, "water": 0, "mood": {}, "xp_earned": 0, "completion_pct": 0})

@app.route('/api/today', methods=['POST'])
def save_today():
    today = date.today().isoformat()
    data = request.get_json()
    checks = data.get('checks', {})
    water = data.get('water', 0)
    mood = data.get('mood', {})

    all_items = [(item['id'], sec['xpEach'])
                 for sec in SECTIONS for item in sec['items'] if 'id' in item]
    xp = sum(xp for item_id, xp in all_items if checks.get(item_id))
    done = sum(1 for item_id, _ in all_items if checks.get(item_id))
    pct = round((done / len(all_items)) * 100) if all_items else 0
    if pct == 100:
        xp += 50

    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO daily_log (log_date, checks, water, mood, xp_earned, completion_pct)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (log_date) DO UPDATE SET
                checks = EXCLUDED.checks,
                water = EXCLUDED.water,
                mood = EXCLUDED.mood,
                xp_earned = EXCLUDED.xp_earned,
                completion_pct = EXCLUDED.completion_pct,
                updated_at = CURRENT_TIMESTAMP
        ''', (today, json.dumps(checks), water, json.dumps(mood), xp, pct))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Save error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "xp_earned": xp, "completion_pct": pct})

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = request.args.get('limit', 365, type=int)
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM daily_log ORDER BY log_date DESC LIMIT %s', (limit,))
        rows = c.fetchall()
        conn.close()
        return jsonify([{
            "date": r['log_date'],
            "checks": json.loads(r['checks'] or '{}'),
            "water": r['water'],
            "mood": json.loads(r['mood'] or '{}'),
            "xp_earned": r['xp_earned'],
            "completion_pct": r['completion_pct'],
        } for r in rows])
    except Exception as e:
        print("History error:", e)
        return jsonify([])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM daily_log ORDER BY log_date DESC')
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print("Stats error:", e)
        return jsonify({"totalDays": 0, "totalXP": 0, "currentStreak": 0,
                        "bestStreak": 0, "avgCompletion": 0, "perfectDays": 0,
                        "categoryAverages": {}, "weekdayAverages": [0]*7})

    if not rows:
        return jsonify({"totalDays": 0, "totalXP": 0, "currentStreak": 0,
                        "bestStreak": 0, "avgCompletion": 0, "perfectDays": 0,
                        "categoryAverages": {}, "weekdayAverages": [0]*7})

    days = [{"date": r['log_date'], "pct": r['completion_pct'],
             "xp": r['xp_earned'], "checks": json.loads(r['checks'] or '{}'),
             "mood": json.loads(r['mood'] or '{}')} for r in rows]

    total_xp = sum(d['xp'] for d in days)
    total_days = len(days)
    perfect_days = sum(1 for d in days if d['pct'] == 100)
    avg_completion = round(sum(d['pct'] for d in days) / total_days) if total_days else 0

    sorted_dates = sorted([d['date'] for d in days])
    best_streak = run = 0
    for i, dt in enumerate(sorted_dates):
        pct = next((x['pct'] for x in days if x['date'] == dt), 0)
        if pct >= 50:
            run += 1 if i > 0 and (
                datetime.strptime(dt, '%Y-%m-%d').date() -
                datetime.strptime(sorted_dates[i-1], '%Y-%m-%d').date()
            ).days == 1 else 1
            best_streak = max(best_streak, run)
        else:
            run = 0

    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    current_streak = 0
    last_date = sorted_dates[-1] if sorted_dates else None
    if last_date in (today_str, yesterday_str):
        check_date = date.today() if last_date == today_str else date.today() - timedelta(days=1)
        for _ in range(total_days):
            ds = check_date.isoformat()
            day_data = next((x for x in days if x['date'] == ds), None)
            if day_data and day_data['pct'] >= 50:
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break

    cat_avgs = {}
    for sec in SECTIONS:
        items = [i for i in sec['items'] if 'id' in i]
        if items:
            avg = sum(
                sum(1 for item in items if d['checks'].get(item['id'])) / len(items) * 100
                for d in days
            ) / len(days)
            cat_avgs[sec['id']] = round(avg)

    weekday_data = {i: {'sum': 0, 'count': 0} for i in range(7)}
    for d in days:
        dt = datetime.strptime(d['date'], '%Y-%m-%d')
        dow = dt.weekday()
        weekday_data[dow]['sum'] += d['pct']
        weekday_data[dow]['count'] += 1
    weekday_avgs = [
        round(weekday_data[i]['sum'] / weekday_data[i]['count'])
        if weekday_data[i]['count'] > 0 else 0 for i in range(7)
    ]

    return jsonify({
        "totalDays": total_days, "totalXP": total_xp,
        "currentStreak": current_streak, "bestStreak": best_streak,
        "avgCompletion": avg_completion, "perfectDays": perfect_days,
        "categoryAverages": cat_avgs, "weekdayAverages": weekday_avgs,
    })

@app.route('/api/chart/completion', methods=['GET'])
def get_chart_completion():
    days_back = request.args.get('days', 30, type=int)
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT log_date, completion_pct FROM daily_log WHERE log_date >= %s ORDER BY log_date ASC', (cutoff,))
        rows = c.fetchall()
        conn.close()
        return jsonify([{"date": r['log_date'], "pct": r['completion_pct']} for r in rows])
    except Exception as e:
        return jsonify([])

@app.route('/api/chart/mood', methods=['GET'])
def get_chart_mood():
    days_back = request.args.get('days', 30, type=int)
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT log_date, mood FROM daily_log WHERE log_date >= %s ORDER BY log_date ASC', (cutoff,))
        rows = c.fetchall()
        conn.close()
        return jsonify([{"date": r['log_date'], **json.loads(r['mood'] or '{}')} for r in rows])
    except Exception as e:
        return jsonify([])

@app.route('/api/version', methods=['GET'])
def get_version():
    return jsonify({"version": PROTOCOL_VERSION, "notes": PROTOCOL_NOTES})

def get_brooklyn_time():
    """Get current Brooklyn time as a readable string."""
    try:
        if HAS_PYTZ:
            tz = pytz.timezone('America/New_York')
            now = datetime.now(tz)
        else:
            now = datetime.utcnow()
        return now.strftime('%A, %B %-d, %Y at %-I:%M %p') + (' ET' if HAS_PYTZ else ' UTC')
    except Exception:
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')


@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({"ok": True})

@app.route('/api/ask', methods=['POST'])
def ask_claude():
    try:
        import urllib.request, json as _json
        data = request.get_json()
        messages = data.get('messages', [])
        context = data.get('context', '')

        if not messages:
            return jsonify({'error': 'No messages provided'}), 400

        # Detect if question needs real-time data
        last_msg = messages[-1].get('content', '').lower()
        needs_search = any(kw in last_msg for kw in [
            'weather', 'temperature', 'forecast', 'rain', 'snow', 'today', 'tonight',
            'news', 'latest', 'current', 'recent', 'right now', 'this week',
            'research', 'study', 'published', 'new treatment', 'clinical trial',
            'nyc', 'brooklyn', 'accident', 'alert', 'open', 'closed', 'hours'
        ])

        current_time = get_brooklyn_time()
        live_context = f"Current time in Brooklyn: {current_time}\n\n"
        full_system = live_context + context

        # Use haiku for simple questions, sonnet for complex/search
        model = "claude-haiku-4-5" if (not needs_search and len(last_msg) < 80) else "claude-sonnet-4-20250514"

        payload_dict = {
            "model": model,
            "max_tokens": 800,
            "system": full_system,
            "messages": messages
        }

        # Only add web search when needed
        if needs_search:
            payload_dict["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
            payload_dict["max_tokens"] = 1024

        payload = _json.dumps(payload_dict).encode()

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'x-api-key': os.environ.get('ANTHROPIC_API_KEY', '')
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = _json.loads(resp.read())

        reply = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                reply += block.get('text', '')

        return jsonify({
            'reply': reply.strip() or 'No response received.',
            'model': model,
            'searched': needs_search
        })

    except Exception as e:
        print("Ask Claude error:", e)
        return jsonify({'error': str(e), 'reply': 'Sorry, I could not connect to Claude. Please try again.'})

@app.route('/api/bike-news', methods=['GET'])
def bike_news():
    try:
        import urllib.request, json as _json
        # Use Claude to summarize recent NYC cycling safety news via web search
        payload = _json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{
                "role": "user",
                "content": "Search for the most recent NYC bicycle accident news, cyclist safety updates, and dangerous intersection reports from the last 30 days. Return a JSON array of 5-8 items. Each item has: 'title' (one sentence summary of the news, max 120 chars) and 'meta' (date or source, max 60 chars). Return ONLY valid JSON array, no other text, no markdown."
            }]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'anthropic-beta': 'interleaved-thinking-2025-05-14'
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        # Extract text from response
        text = ''
        for block in data.get('content', []):
            if block.get('type') == 'text':
                text += block.get('text', '')
        # Parse JSON from text
        text = text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        items = _json.loads(text.strip())
        return jsonify({'items': items, 'cached': False})
    except Exception as e:
        print("Bike news error:", e)
        # Fallback static items
        return jsonify({'items': [
            {'title': 'NYC DOT Vision Zero: 2025 saw 14 cyclist fatalities through Q3 — down 18% from 2024', 'meta': 'NYC DOT Vision Zero Report'},
            {'title': 'Brooklyn: Atlantic Ave corridor flagged for protected lane extension after 3 incidents near 4th Ave', 'meta': 'NYC Streets Blog 2025'},
            {'title': 'Manhattan Bridge bike path gets improved lighting after cyclist collision near Delancey St exit', 'meta': 'Gothamist 2025'},
            {'title': 'Williamsburg Kent Ave: DOT adds plastic bollards after truck-cyclist near-miss series', 'meta': 'Transportation Alternatives 2025'},
            {'title': 'NYC e-bike registration law takes effect — unregistered throttle e-bikes subject to $500 fine', 'meta': 'NYC Local Law 2025'},
        ], 'cached': True})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": PROTOCOL_VERSION})

@app.route('/api/claude_context')
def api_claude_context():
    """Assembles Jack's clinical context for Claude queries."""
    import json

    # Build protocol summary from SECTIONS
    protocol_lines = []
    for section in SECTIONS:
        protocol_lines.append(f"\n[{section.get('title', section.get('id',''))}]")
        for item in section.get('items', []):
            tag = item.get('tagLabel', '')
            note = item.get('note', '')[:150]
            protocol_lines.append(f"  {'⚠ ' if tag in ('Critical','Avoid') else '• '}{item['label']}{f' ({tag})' if tag else ''}")
            if note:
                protocol_lines.append(f"      {note}")

    context = """PATIENT: Jack Wiggins, age 25, Brooklyn NY. NYU Psychology graduate. Son of Noel Wiggins.

GENETICS (KEY):
- MTHFR C677T HOMOZYGOUS (both copies) — severe methylation impairment. Most critical finding.
- COMT Val/Val — slow dopamine breakdown in prefrontal cortex. Sensitive to stress, caffeine, stimulants.
- SLC6A4 variant — serotonin transporter. Influences SSRI response.
- MTRR A66G — methionine synthase reductase. Compounds MTHFR methylation deficit.

CURRENT MEDICATIONS & SUPPLEMENTS:
- Enlyte (Rx): L-methylfolate 7mg + folinic acid 3.5mg + adenosylcobalamin B12 50mcg + P5P trace
- Guanfacine 4mg (prescribed) — prefrontal/ADHD support, synergistic with TMS
- Vitamin D3 5,000 IU + K2 100mcg daily with fat
- Fish oil 2-3g EPA with largest meal
- Vitamin E 400 IU (mixed tocopherols) with dinner
- Magnesium glycinate 300-400mg at 9:45 PM
- Melatonin 0.3-0.5mg at 9 PM (Phase 2 — after established on magnesium)

KEY AVOID:
- Synthetic folic acid (fortified cereals, enriched breads) — competes with Enlyte methylfolate receptors
- High-dose melatonin (5-10mg gummies) — testosterone risk
- French press / espresso — diterpenes raise homocysteine
- Green tea within 45 min of Enlyte — tannins reduce methylfolate absorption
- THC on TMS days

ACTIVE TREATMENT:
- TMS (Transcranial Magnetic Stimulation) — prescribed, scheduled sessions
- Protocol designed to support TMS neuroplasticity: exercise within 2 hrs of TMS amplifies response

CLINICAL HYPOTHESIS (7 evidence-based factors):
1. MTHFR C677T homozygous — impaired methylation → low SAM → low serotonin/dopamine synthesis
2. COMT Val/Val — slow prefrontal dopamine breakdown → reward circuit dysregulation
3. Elevated homocysteine (was elevated) — neurotoxic, correlates with depression severity
4. Low Vitamin D (was insufficient in 2020 labs) — neuroinflammation, mood regulation
5. Vitamin E deficiency (2020) — antioxidant capacity, myelin integrity
6. Mitochondrial dysfunction — supports red light sauna, cold plunge protocol
7. Circadian dysregulation — anchor sleep protocol (10:30 PM / 9:00 AM)

PROTOCOL HIGHLIGHTS:
""" + '\n'.join(protocol_lines)

    return jsonify({'context': context, 'version': PROTOCOL_VERSION})


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
