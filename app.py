import os
import json
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ── DATABASE ──────────────────────────────────────────────
DB_PATH = os.environ.get('DB_PATH', '/data/wellness.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL UNIQUE,
            checks TEXT DEFAULT '{}',
            water INTEGER DEFAULT 0,
            mood TEXT DEFAULT '{}',
            xp_earned INTEGER DEFAULT 0,
            completion_pct INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS protocol_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            deployed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized at", DB_PATH)

# ── PROTOCOL DATA ─────────────────────────────────────────
# This is the single source of truth for the checklist.
# Update this dict and redeploy to add/remove/change items.
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
            {"id": "s2", "label": "Woke at 7:00 AM — no snooze", "note": "Same time 7 days a week — circadian anchor for dopamine cycle", "tag": "crit", "tagLabel": "Critical"},
            {"id": "s3", "label": "10 min outdoor morning light within 30 min of waking", "note": "No sunglasses · resets circadian clock · boosts dopamine + cortisol rhythm", "tag": "key", "tagLabel": "Key"},
        ]
    },
    {
        "id": "morning",
        "icon": "🌄",
        "title": "Morning Routine",
        "color": "morning",
        "xpEach": 2,
        "items": [
            {"id": "m1", "label": "16 oz water immediately on waking (7:00 AM)", "note": "Before anything else · pinch of sea salt · rehydrates overnight depletion · starts homocysteine clearance", "tag": "daily", "tagLabel": "Daily"},
            {"id": "m6", "label": "10 min outdoor light + red light sauna 15 min (home unit)", "note": "COMT Val/Val: morning light + red light + movement is your most powerful dopamine stack. Red light sauna first (mitochondrial ATP, prefrontal support, circadian signal) then outdoor light. Both before cycling.", "tag": "crit", "tagLabel": "9:05–9:20 AM"},
            {"id": "m7", "label": "Cycling: 20–30 min moderate pace (Prospect Park or stationary)", "note": "Core daily feature — not optional. Moderate pace only (can talk but slightly breathless). Cycling within 2 hrs of TMS significantly amplifies neuroplasticity. Raises prefrontal dopamine for Val/Val COMT. Lowers homocysteine. Improves HDL.", "tag": "crit", "tagLabel": "7:10–7:40 AM"},
            {"id": "m2", "label": "Breakfast — 2 eggs + greens + berries", "note": "After cycling · eggs (choline) · spinach/arugula (natural folate) · blueberries (anti-neuroinflammation) · eat within 45 min of finishing exercise", "tag": "key", "tagLabel": "~7:45 AM"},
            {"id": "m3", "label": "Morning supplements taken with breakfast", "note": "Enlyte · D3/K2 · Fish oil — with food · D3 and fish oil require fat to absorb", "tag": "crit", "tagLabel": "Critical"},
            {"id": "m8", "label": "1 cup filtered drip coffee with or after breakfast", "note": "Filtered only — not French press or espresso (diterpenes raise homocysteine) · with food not on empty stomach · your CYP1A2 is highly inducible from smoking = faster metabolism + harder crash · 1 cup max · STOP by 10:30 AM", "tag": "key", "tagLabel": "~7:45 AM"},
            {"id": "m4", "label": "Green tea Cup 1 — 45–60 min AFTER Enlyte (~8:45 AM)", "note": "Wait 45-60 min after Enlyte — tannins reduce methylfolate absorption · brew at 170F for 1-2 min · Japanese sencha preferred for L-theanine · L-theanine + caffeine = calm focus without anxiety spike", "tag": "key", "tagLabel": "~8:45 AM"},
        ]
    },
    {
        "id": "supplements",
        "icon": "💊",
        "title": "Supplements",
        "color": "supplements",
        "xpEach": 4,
        "items": [
            {"id": "sup1", "label": "Enlyte — 1 capsule with breakfast", "note": "L-methylfolate 7.5mg + methyl-B12 + P5P + NAC · most critical intervention for MTHFR C677T homozygous", "tag": "crit", "tagLabel": "Critical"},
            {"id": "sup2", "label": "Vitamin D3 5,000 IU + K2 100mcg with breakfast", "note": "Take with fat · was insufficient in 2020 labs · target 50–70 ng/mL", "tag": "crit", "tagLabel": "Critical"},
            {"id": "sup3", "label": "Fish oil 2–3g EPA with largest meal", "note": "EPA:DHA ratio favoring EPA · raises HDL · antidepressant evidence for COMT Val/Val", "tag": "key", "tagLabel": "Key"},
            {"id": "sup4", "label": "Vitamin E 400 IU (mixed tocopherols) with dinner", "note": "Was deficient in 2020 labs · take with fat · mixed not alpha-only", "tag": "daily", "tagLabel": "Daily"},
            {"id": "sup5", "label": "Magnesium glycinate 300–400mg at 9:45 PM", "note": "Glycinate form only · GABA support · lowers cortisol · supports methylation · START HERE before melatonin", "tag": "crit", "tagLabel": "9:45 PM"},
            {"id": "sup6", "label": "Melatonin 0.3–0.5mg at 9:00 PM — Phase 2 only", "note": "⚠️ Start ONLY after 2–3 weeks on magnesium. 0.3–0.5mg ONLY — no gummies (testosterone risk at 5–10mg). COMT report recommends for homocysteine. Pure Encapsulations 0.5mg or Life Extension 0.3mg.", "tag": "phase2", "tagLabel": "Phase 2"},
            {"id": "sup7", "label": "Guanfacine 4mg as prescribed", "note": "As prescribed — works synergistically with TMS for prefrontal function", "tag": "rx", "tagLabel": "Rx"},
            {"id": "sup8", "label": "No synthetic folic acid today", "note": "❌ No fortified cereal, enriched bread, folic acid supplements — competes with Enlyte at methylfolate receptors", "tag": "avoid", "tagLabel": "Avoid"},
        ]
    },
    {
        "id": "meals",
        "icon": "🥗",
        "title": "Meals",
        "color": "meals",
        "xpEach": 2,
        "items": [
            {"id": "f1", "label": "Breakfast: 2 whole eggs (not just whites)", "note": "Choline source — supports methylation pathway directly", "tag": "crit", "tagLabel": "Must", "dividerBefore": "🌅 Breakfast 7:30–8:00 AM"},
            {"id": "f2", "label": "Breakfast: Large handful dark leafy greens", "note": "Natural food folate — sauté with eggs or raw", "tag": "key", "tagLabel": "Key"},
            {"id": "f3", "label": "Breakfast: ½ cup berries (blueberries preferred)", "note": "Anthocyanins reduce neuroinflammation · low glycemic · prefrontal cortex support", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f4", "label": "Lunch: Large salad with protein", "note": "Lentils/chickpeas/chicken/turkey/salmon · tyrosine for dopamine synthesis — essential for COMT Val/Val", "tag": "crit", "tagLabel": "Must", "dividerBefore": "☀️ Lunch 12:30–1:00 PM"},
            {"id": "f5", "label": "Lunch: Olive oil dressing + pumpkin seeds", "note": "Pumpkin seeds: zinc + magnesium + tyrosine · olive oil supports HDL", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f6", "label": "Green tea Cup 2 — 60 min after lunch (~1:30 PM)", "note": "Midday focus lift · L-theanine prevents anxiety spike · LAST caffeine of day · no caffeine after 2 PM", "tag": "key", "tagLabel": "~1:30 PM"},
            {"id": "f7", "label": "Dinner: Fatty fish (salmon/mackerel/sardines) OR turkey", "note": "3–4x per week fatty fish minimum · EPA/DHA raises HDL · amplifies TMS response", "tag": "crit", "tagLabel": "Priority", "dividerBefore": "🌙 Dinner 6:30–7:00 PM (finish by 7:30)"},
            {"id": "f8", "label": "Dinner: Beets or asparagus as side", "note": "Beets: betaine directly bypasses MTHFR — lowers homocysteine independently. Asparagus: highest food folate.", "tag": "key", "tagLabel": "Key"},
            {"id": "f9", "label": "Dinner: Cooked vegetable in olive oil only", "note": "No seed oils (canola/soybean/corn) — olive oil or butter only", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f10", "label": "Snack: Walnuts (small handful) midday", "note": "Plant omega-3s · melatonin precursors · COMT Val/Val cognitive support per genetic report", "tag": "daily", "tagLabel": "Daily", "dividerBefore": "🍎 Snacks"},
            {"id": "f11", "label": "Snack: Plain full-fat yogurt OR kefir — never flavored", "note": "Kefir preferred — broadest probiotic profile · gut-brain axis · tyrosine for dopamine · B12 · zero IgE dairy allergy confirmed 2020 labs · NO flavored varieties (15-25g sugar negates all benefit)", "tag": "daily", "tagLabel": "Daily"},
            {"id": "f14", "label": "Fruit: whole fruit only — no juice", "note": "Whole fruit OK daily (fiber intact) · berries preferred · NO commercial juice: concentrated sugar, often folic-acid fortified, zero fiber · Fresh lemon/lime squeeze on food is fine", "tag": "key", "tagLabel": "Key"},
            {"id": "f15", "label": "Full-fat dairy always over low-fat", "note": "Fat-soluble vitamins D3/E/K2 need dietary fat to absorb · full-fat supports HDL · hard aged cheese (parmesan/cheddar/gruyere) fine in moderation — high tyrosine + B12 + zinc", "tag": "daily", "tagLabel": "Daily", "dividerBefore": "🥛 Dairy Guide"},
            {"id": "f12", "label": "Avoided: fortified cereal, white bread, enriched pasta", "note": "Synthetic folic acid competes with Enlyte methylfolate receptors — critical for MTHFR C677T homozygous", "tag": "avoid", "tagLabel": "Avoid", "dividerBefore": "🚫 Avoid Today"},
            {"id": "f13", "label": "Avoided: commercial fruit juice, sugary drinks, or soda", "note": "Juice: blood sugar spike + often folic-acid fortified + zero fiber · Blood sugar instability directly worsens OCD and anxiety · Whole fruit only", "tag": "avoid", "tagLabel": "Avoid"},
            {"id": "f16", "label": "Avoided: flavored yogurt (Chobani fruit, Yoplait, etc.)", "note": "15-25g added sugar per serving negates all probiotic benefit · same glucose spike as juice · plain only", "tag": "avoid", "tagLabel": "Avoid"},
            {"id": "f17", "label": "Avoided: processed cheese (American slices, Velveeta, spreads)", "note": "Heavily processed · additives · high sodium · use real aged cheese instead", "tag": "avoid", "tagLabel": "Avoid"},
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
            {"id": "h5", "label": "Coconut water: post-exercise only — 1 cup max", "note": "Good post-workout electrolytes (potassium/magnesium) · better than sports drinks · BUT 9-11g sugar per cup means NOT for all-day hydration · your glucose has been volatile across labs · use water + electrolyte drops (ConcenTrace or LMNT) for daily hydration instead", "tag": "key", "tagLabel": "Post-exercise"},
            {"id": "h2", "label": "Coffee already had this morning — no more after 10:30 AM", "note": "Coffee is now a structured morning item (with breakfast) · this is your reminder that the window is closed · filtered drip only · your CYP1A2 from smoking means caffeine crashes harder and faster than average", "tag": "key", "tagLabel": "Reminder"},
            {"id": "h3", "label": "No caffeine after 2:00 PM", "note": "5-7 hr half-life means afternoon caffeine disrupts 10:30 PM bedtime · hard stop", "tag": "crit", "tagLabel": "Hard stop"},
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
            {"id": "e1", "label": "Morning cycling DONE (logged in morning routine)", "note": "Core daily ride already completed in morning block 7:10–7:40 AM · this confirms it happened · if missed this morning: do it now before 2 PM — still before TMS window", "tag": "crit", "tagLabel": "Core"},
            {"id": "e5", "label": "Resistance training 20–30 min (Tue/Thu)", "note": "Bodyweight at home: squats/pushups/lunges/planks/dips · raises BDNF · amplifies TMS neuroplasticity · antidepressant evidence comparable to SSRIs · do AFTER cycling not instead of", "tag": "key", "tagLabel": "Tue/Thu"},
            {"id": "e6", "label": "Second short walk or cycle 15–20 min (afternoon, optional)", "note": "Optional but powerful on TMS days — BDNF peaks again 90-120 min after second session · Prospect Park, errands on bike, or 15 min stationary · keep moderate pace", "tag": "daily", "tagLabel": "Optional"},
            {"id": "e2", "label": "Yoga or stretching 30 min (Saturday)", "note": "Yoga Nidra or restorative yoga · activates parasympathetic system · directly counters OCD hypervigilance · lowers cortisol · Yoga with Adriene on YouTube free", "tag": "daily", "tagLabel": "Saturday"},
            {"id": "e4", "label": "Did not smoke more than yesterday", "note": "Each cigarette depletes folate + Vitamin C · raises homocysteine · reduces Enlyte effectiveness · goal: reduce 1 per week toward zero", "tag": "crit", "tagLabel": "Reduce"},
            {"id": "e4", "label": "Did not smoke more than yesterday", "note": "Each cigarette depletes folate + Vitamin C · raises homocysteine · reduces Enlyte effectiveness. Goal: reduce 1 per week → zero.", "tag": "crit", "tagLabel": "Reduce"},
        ]
    },
    {
        "id": "tms",
        "icon": "🧠",
        "title": "TMS & Treatment",
        "color": "tms",
        "xpEach": 4,
        "items": [
            {"id": "t1", "label": "TMS session attended (if scheduled today)", "note": "Take supplements before session · methylfolate supports neurotransmitter substrate · exercise within a few hours amplifies neuroplasticity · no THC on TMS days", "tag": "crit", "tagLabel": "Priority"},
            {"id": "t2", "label": "Post-TMS: 20 min rest or gentle walk", "note": "Allow neuroplasticity window to consolidate · avoid stressful stimuli 30 min after · no THC (reduces cortical excitability TMS is trying to enhance)", "tag": "key", "tagLabel": "Key"},
            {"id": "t3", "label": "Guanfacine taken as prescribed", "note": "Rx compliance critical — works synergistically with TMS for prefrontal function", "tag": "rx", "tagLabel": "Rx"},
            {"id": "t4", "label": "Therapy / ERP session (if scheduled)", "note": "Exposure and Response Prevention is gold standard for OCD alongside pharmacological and TMS support", "tag": "key", "tagLabel": "Key"},
        ]
    },
    {
        "id": "recovery",
        "icon": "🔥",
        "title": "Recovery & Optimization",
        "color": "recovery",
        "xpEach": 4,
        "items": [
            {"id": "rec1", "label": "Red light sauna — home (daily, any day)", "note": "20 min at 80-100C · red/NIR wavelengths support mitochondrial ATP for methylation · prefrontal oxygenation · antidepressant mechanism via serotonin pathways · lower temp than bathhouse but photobiomodulation benefit is the key advantage here · do not use within 2 hrs of bedtime", "tag": "crit", "tagLabel": "Daily"},
            {"id": "rec2", "label": "Bathhouse sauna + cold plunge (3x this week — Mon/Wed/Fri suggested)", "note": "Hotter sauna (90-100C) produces stronger dopamine and norepinephrine response than home unit · cold plunge immediately after: dopamine +300% sustained for 2-3 hrs · contrast therapy (2-3 rounds sauna/plunge) is the most powerful non-pharmacological dopamine protocol available for COMT Val/Val · post-sauna is your best use for coconut water electrolytes", "tag": "key", "tagLabel": "3x/week"},
            {"id": "rec3", "label": "Cold shower or plunge — daily minimum on home days", "note": "On days not at bathhouse: end morning shower with 60-90 sec cold water · real dopamine and norepinephrine response even from shower cold · pairs with cycling and red light for morning dopamine stack · enter slowly — guanfacine lowers BP, cold spikes it briefly", "tag": "daily", "tagLabel": "Daily"},
            {"id": "rec4", "label": "Red light before TMS today (if TMS scheduled)", "note": "10-15 min NIR/red light applied to forehead and scalp before TMS session · supports mitochondrial energy in prefrontal neurons that TMS will stimulate · complementary mechanisms — no interference · leave 60-90 min between sauna and TMS for core temp to normalize", "tag": "key", "tagLabel": "TMS days"},
            {"id": "rec5", "label": "Sauna timing: not within 2 hours of bedtime", "note": "Core temperature must drop to initiate melatonin onset and sleep · sauna too close to bed disrupts your 10:30 PM sleep anchor · schedule home sauna before 7:30 PM if doing an evening session", "tag": "crit", "tagLabel": "Timing"},
            {"id": "rec6", "label": "Post-sauna hydration: water + electrolytes immediately after", "note": "Significant fluid and electrolyte loss from every session · 16-24 oz water with ConcenTrace drops or LMNT straight after · this is the correct moment for coconut water (1 cup) if you want it — post-sauna electrolyte replacement is its legitimate use", "tag": "daily", "tagLabel": "Always"},
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
            {"id": "ev3", "label": "9:00 PM — Melatonin 0.3–0.5mg (Phase 2 only)", "note": "Circadian signal not sedative · 90 min before bed · start after 2–3 wks on magnesium · 0.3–0.5mg ONLY — no gummies (testosterone risk at high dose) · COMT report supports for homocysteine", "tag": "phase2", "tagLabel": "Phase 2"},
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/protocol', methods=['GET'])
def get_protocol():
    """Return the current protocol definition."""
    return jsonify({
        "version": PROTOCOL_VERSION,
        "notes": PROTOCOL_NOTES,
        "sections": SECTIONS,
        "levels": LEVELS,
        "moodKeys": MOOD_KEYS,
    })

@app.route('/api/today', methods=['GET'])
def get_today():
    """Get today's log entry."""
    today = date.today().isoformat()
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM daily_log WHERE log_date = ?', (today,)
    ).fetchone()
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
    else:
        return jsonify({
            "date": today,
            "checks": {},
            "water": 0,
            "mood": {},
            "xp_earned": 0,
            "completion_pct": 0,
        })

@app.route('/api/today', methods=['POST'])
def save_today():
    """Save or update today's log."""
    today = date.today().isoformat()
    data = request.get_json()
    
    checks = data.get('checks', {})
    water = data.get('water', 0)
    mood = data.get('mood', {})
    
    # Calculate XP and completion
    all_items = []
    for sec in SECTIONS:
        for item in sec['items']:
            if 'id' in item:
                all_items.append((item['id'], sec['xpEach']))
    
    xp = sum(xp for item_id, xp in all_items if checks.get(item_id))
    done = sum(1 for item_id, _ in all_items if checks.get(item_id))
    pct = round((done / len(all_items)) * 100) if all_items else 0
    
    # Streak bonus
    if pct == 100:
        xp += 50
    
    conn = get_db()
    conn.execute('''
        INSERT INTO daily_log (log_date, checks, water, mood, xp_earned, completion_pct, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(log_date) DO UPDATE SET
            checks = excluded.checks,
            water = excluded.water,
            mood = excluded.mood,
            xp_earned = excluded.xp_earned,
            completion_pct = excluded.completion_pct,
            updated_at = CURRENT_TIMESTAMP
    ''', (today, json.dumps(checks), water, json.dumps(mood), xp, pct))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "xp_earned": xp, "completion_pct": pct})

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get all historical log entries."""
    limit = request.args.get('limit', 365, type=int)
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM daily_log ORDER BY log_date DESC LIMIT ?', (limit,)
    ).fetchall()
    conn.close()
    
    result = []
    for row in rows:
        result.append({
            "date": row['log_date'],
            "checks": json.loads(row['checks'] or '{}'),
            "water": row['water'],
            "mood": json.loads(row['mood'] or '{}'),
            "xp_earned": row['xp_earned'],
            "completion_pct": row['completion_pct'],
        })
    
    return jsonify(result)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Compute aggregate stats."""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM daily_log ORDER BY log_date DESC'
    ).fetchall()
    conn.close()
    
    if not rows:
        return jsonify({
            "totalDays": 0, "totalXP": 0, "currentStreak": 0,
            "bestStreak": 0, "avgCompletion": 0, "perfectDays": 0,
        })
    
    days = [{"date": r['log_date'], "pct": r['completion_pct'], "xp": r['xp_earned'],
             "mood": json.loads(r['mood'] or '{}')} for r in rows]
    
    total_xp = sum(d['xp'] for d in days)
    total_days = len(days)
    perfect_days = sum(1 for d in days if d['pct'] == 100)
    avg_completion = round(sum(d['pct'] for d in days) / total_days) if total_days else 0
    
    # Streak calculation
    sorted_dates = sorted([d['date'] for d in days])
    current_streak = 0
    best_streak = 0
    run = 0
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    
    for i, d in enumerate(sorted_dates):
        pct = next((x['pct'] for x in days if x['date'] == d), 0)
        if pct >= 50:
            if i == 0:
                run = 1
            else:
                prev = sorted_dates[i-1]
                prev_date = datetime.strptime(prev, '%Y-%m-%d').date()
                curr_date = datetime.strptime(d, '%Y-%m-%d').date()
                if (curr_date - prev_date).days == 1:
                    run += 1
                else:
                    run = 1
            best_streak = max(best_streak, run)
        else:
            run = 0
    
    # Current streak: count back from today/yesterday
    last_date = sorted_dates[-1] if sorted_dates else None
    if last_date in (today_str, yesterday_str):
        streak = 0
        check_date = date.today() if last_date == today_str else date.today() - timedelta(days=1)
        for _ in range(total_days):
            ds = check_date.isoformat()
            day_data = next((x for x in days if x['date'] == ds), None)
            if day_data and day_data['pct'] >= 50:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        current_streak = streak
    
    # Category averages
    cat_avgs = {}
    all_logs = [{"checks": json.loads(r['checks'] or '{}')} for r in rows]
    for sec in SECTIONS:
        items = [i for i in sec['items'] if 'id' in i]
        if items and all_logs:
            avg = sum(
                sum(1 for item in items if log['checks'].get(item['id'])) / len(items) * 100
                for log in all_logs
            ) / len(all_logs)
            cat_avgs[sec['id']] = round(avg)
    
    # Weekday breakdown
    weekday_data = {i: {'sum': 0, 'count': 0} for i in range(7)}
    for d in days:
        dt = datetime.strptime(d['date'], '%Y-%m-%d')
        dow = dt.weekday()  # 0=Mon
        weekday_data[dow]['sum'] += d['pct']
        weekday_data[dow]['count'] += 1
    
    weekday_avgs = [
        round(weekday_data[i]['sum'] / weekday_data[i]['count'])
        if weekday_data[i]['count'] > 0 else 0
        for i in range(7)
    ]
    
    return jsonify({
        "totalDays": total_days,
        "totalXP": total_xp,
        "currentStreak": current_streak,
        "bestStreak": best_streak,
        "avgCompletion": avg_completion,
        "perfectDays": perfect_days,
        "categoryAverages": cat_avgs,
        "weekdayAverages": weekday_avgs,
    })

@app.route('/api/chart/completion', methods=['GET'])
def get_chart_completion():
    """Get completion data for charts."""
    days_back = request.args.get('days', 30, type=int)
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    
    conn = get_db()
    rows = conn.execute(
        'SELECT log_date, completion_pct FROM daily_log WHERE log_date >= ? ORDER BY log_date ASC',
        (cutoff,)
    ).fetchall()
    conn.close()
    
    return jsonify([{"date": r['log_date'], "pct": r['completion_pct']} for r in rows])

@app.route('/api/chart/mood', methods=['GET'])
def get_chart_mood():
    """Get mood data for charts."""
    days_back = request.args.get('days', 30, type=int)
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    
    conn = get_db()
    rows = conn.execute(
        'SELECT log_date, mood FROM daily_log WHERE log_date >= ? ORDER BY log_date ASC',
        (cutoff,)
    ).fetchall()
    conn.close()
    
    result = []
    for r in rows:
        mood_data = json.loads(r['mood'] or '{}')
        result.append({
            "date": r['log_date'],
            **mood_data
        })
    
    return jsonify(result)

@app.route('/api/version', methods=['GET'])
def get_version():
    return jsonify({
        "version": PROTOCOL_VERSION,
        "notes": PROTOCOL_NOTES,
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": PROTOCOL_VERSION})

# ── STARTUP ───────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
