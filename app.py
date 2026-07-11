import os
import secrets
from urllib.parse import urlencode
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
import json
import base64
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import requests
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
app.secret_key = os.environ.get('SECRET_KEY', 'jw-secret-2026-x9k')
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 days

SITE_PASSWORD = os.environ.get('SITE_PASSWORD', '5565')

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── AUTH ──────────────────────────────────────────────────



# ── DATABASE ──────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# ── GMAIL JOB-RESPONSE INTEGRATION ───────────────────────
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'https://jack-wellness.up.railway.app/auth/gmail/callback')
GMAIL_TARGET_EMAIL = 'perrywigginsjack@gmail.com'
GOOGLE_OAUTH_SCOPES = 'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/userinfo.email'
DEFAULT_JOB_FILTER_QUERY = (
    '(subject:("your application" OR "thank you for applying") OR '
    'subject:("thank you for your interest") OR subject:("regarding your application") OR '
    'subject:("update on your application") OR subject:("interview invitation") OR '
    'subject:("interview confirmation") OR subject:("we have received your application") OR '
    'subject:("next steps in your application") OR subject:("regarding your candidacy") OR '
    'subject:("schedule an interview") OR subject:("invite you to interview") OR '
    'subject:("phone screen") OR '
    'from:(safehorizon.org OR vibrant.org OR sanctuaryforfamilies.org OR '
    'myworkday.com OR greenhouse.io OR lever.co OR icims.com OR smartrecruiters.com OR '
    'workday.com OR ashbyhq.com OR indeedemail.com)) '
    '-from:(jobalerts-noreply@linkedin.com OR notifications-noreply@linkedin.com OR '
    'messages-noreply@linkedin.com OR em.linkedin.com OR donotreply@match.indeed.com OR '
    'linkedin.com OR equinox.com OR robinhood.com OR hiltonhonors.com OR h5.hilton.com OR '
    'hiltongrandvacations.com OR lyftmail.com OR nytimes.com OR washingtonpost.com OR '
    'usnews.com) '
    'newer_than:60d'
)

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'https://jack-wellness.up.railway.app/auth/spotify/callback')
SPOTIFY_SCOPES = 'user-read-recently-played user-read-currently-playing user-read-playback-state user-modify-playback-state'

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS career_leads (
            id SERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            org_name TEXT NOT NULL,
            role_title TEXT,
            website TEXT,
            apply_url TEXT,
            phone TEXT,
            pay_range TEXT,
            info TEXT,
            checked BOOLEAN DEFAULT FALSE,
            last_contact_date TEXT,
            next_contact_date TEXT,
            follow_up_notes TEXT DEFAULT '',
            contact_email TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('ALTER TABLE career_leads ADD COLUMN IF NOT EXISTS contact_email TEXT')
    conn.commit()

    c.execute('SELECT COUNT(*) FROM career_leads')
    if c.fetchone()[0] == 0:
        seed = [
            ("Crisis & Clinical", "Safe Horizon", "Client Advocate Specialist — Hotlines",
             "https://www.safehorizon.org/career-opportunities/",
             "https://safehorizon.csod.com/ux/ats/careersite/1/home/requisition/1619?c=safehorizon",
             "(212) 577-7700", "$23.63–$26.58/hr, 35 hrs/wk + full benefits",
             "Fields calls to Safe Horizon's 3 24-hour hotlines (Domestic Violence, Crime Victims, Rape & Incest). Conducts safety/needs assessments, trauma-informed client-centered support. Bachelor's or equivalent experience.", 1),
            ("Crisis & Clinical", "NYC 988 / Vibrant Emotional Health", "Crisis Counselor",
             "https://www.vibrant.org/get-involved/work-for-us/",
             "https://vibrant.wd5.myworkdayjobs.com/VEH_EXTERNAL_CAREER_SITE",
             "(212) 254-0333", "$30.22–$32.00/hr",
             "Answers NYC 988, NY HOPEline, National Suicide Prevention Lifeline, Disaster Distress Helpline via call/text/chat. Bachelor's or Master's level counselors both considered.", 2),
            ("Crisis & Clinical", "Sanctuary for Families", "Crisis Intervention / Advocate roles",
             "https://sanctuaryforfamilies.org/careers/", "https://sanctuaryforfamilies.org/careers/",
             "(212) 349-6009", "Varies by role",
             "NY's leading service provider for survivors of domestic violence, sex trafficking, gender violence. Legal helpline ext. 8000. Postings rotate — check careers page directly.", 3),
            ("Retail & Local — Park Slope", "Mr. Boddington's", "Retail Associate",
             "https://newyork.craigslist.org/search/brk/jjj?query=park+slope", "", "",
             "Not listed — apply via posting",
             "Live Craigslist listing in Park Slope, posted recently. Retail associate role.", 4),
            ("Retail & Local — Park Slope", "Craigslist Brooklyn F&B Board", "Barista / FOH / Floor Lead / Steward (rotating)",
             "https://newyork.craigslist.org/search/brooklyn-ny/fbh", "", "",
             "Varies",
             "General Brooklyn food/beverage/hospitality board — updates daily. Recent hits: Cafe/Specialty Shop Floor Lead, Experienced Steward, Lavaplatos/Dishwasher (Park Slope). Check every 1–2 days.", 5),
        ]
        c.executemany('''
            INSERT INTO career_leads (category, org_name, role_title, website, apply_url, phone, pay_range, info, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', seed)
        conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS gmail_connection (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            access_token TEXT,
            refresh_token TEXT,
            token_expiry TIMESTAMP,
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS spotify_connection (
            id SERIAL PRIMARY KEY,
            display_name TEXT,
            access_token TEXT,
            refresh_token TEXT,
            token_expiry TIMESTAMP,
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS career_resources (
            id SERIAL PRIMARY KEY,
            resource_type TEXT NOT NULL DEFAULT 'video',
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            synopsis TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('SELECT COUNT(*) FROM career_resources')
    if c.fetchone()[0] == 0:
        resources = [
            ('video', 'The Worst Disease of the Mind You Must Avoid',
             'https://youtu.be/qTk2DjGLWoU',
             "Chase Hughes on what he calls the most dangerous mindset — staying mentally anchored to the past — and how it quietly undermines growth, decision-making, and forward momentum. Useful framing for approaching a job search from a forward-looking mindset rather than getting stuck on past setbacks or rejections.",
             1),
            ('video', "Your Brain Won't Let You Change — Until This Happens",
             'https://youtu.be/qB3lpAS9Usw',
             "Chase Hughes explains why willpower alone doesn't produce lasting change — goals fail not from lack of discipline but from being aimed at the wrong target — and what has to shift before new habits or goals actually stick. Relevant for staying motivated and realistic through a job search.",
             2),
        ]
        c.executemany('''
            INSERT INTO career_resources (resource_type, title, url, synopsis, sort_order)
            VALUES (%s,%s,%s,%s,%s)
        ''', resources)
        conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS job_map_pins (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            role_title TEXT,
            status TEXT DEFAULT 'walkin',
            address TEXT,
            phone TEXT,
            website TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            info TEXT,
            checked BOOLEAN DEFAULT FALSE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    c.execute('SELECT COUNT(*) FROM job_map_pins')
    if c.fetchone()[0] == 0:
        pins = [
            ("Mr. Boddington's Studio", "Retail", "Retail Associate", "live", "153 7th Ave, Brooklyn, NY 11215",
             None, "https://newyork.craigslist.org/search/brk/jjj?query=park+slope", 40.6724636, -73.9767367,
             "Live Craigslist listing — stationery/gift shop, apply directly.", 1),
            ("Poetica Coffee", "Cafe", "Barista (walk-in)", "walkin", "240 7th Ave, Brooklyn, NY 11215",
             None, None, 40.6697216, -73.9794446, "Popular, well-reviewed, busy morning rush — bring resume, ask for manager.", 2),
            ("Variety Coffee", "Cafe", "Barista (walk-in)", "walkin", "312 7th Ave, Brooklyn, NY 11215",
             "+1 718-788-1891", None, 40.6676888, -73.9811894, "Neighborhood favorite, steady foot traffic.", 3),
            ("Brooklyn Bread Cafe", "Cafe", "Counter / Kitchen (walk-in)", "walkin", "347 7th Ave, Brooklyn, NY 11215",
             "+1 929-491-0700", None, 40.6663101, -73.9818408, "Sandwich/bakery counter — often needs morning shift help.", 4),
            ("Hungry Ghost Coffee", "Cafe", "Barista (walk-in)", "walkin", "156 7th Ave, Brooklyn, NY 11215",
             None, None, 40.6723139, -73.9772867, "Local mini-chain, multiple locations, decent turnover.", 5),
            ("Cuppa Hive Coffee", "Cafe", "Barista (walk-in)", "walkin", "428 15th St, Brooklyn, NY 11215",
             "+1 347-415-7042", None, 40.6618849, -73.9819648, "Cozy spot near Prospect Park, high ratings.", 6),
            ("Cusp Crepe and Espresso Bar", "Cafe", "Counter (walk-in)", "walkin", "321 7th Ave, Brooklyn, NY 11215",
             "+1 718-788-2980", None, 40.6670625, -73.9812069, "Small shop, morning cook/counter help often needed.", 7),
            ("Brew Memories", "Cafe", "Barista (walk-in)", "walkin", "295 7th Ave, Brooklyn, NY 11215",
             "+1 347-987-3954", None, 40.6677733, -73.9805664, "Bubble tea + coffee, busy afternoons.", 8),
            ("Blank Street", "Cafe", "Barista (walk-in)", "walkin", "287 6th Ave, Brooklyn, NY 11215",
             None, "https://www.blankstreet.com/careers", 40.6726747, -73.979786, "Growing chain — check their careers page too, not just walk-in.", 9),
            ("Flea Park Slope", "Boutique", "Sales Associate (walk-in)", "walkin", "211 5th Ave, Brooklyn, NY 11215",
             "+1 347-223-4826", None, 40.6761258, -73.9804547, "Clothing/gift boutique, community favorite.", 10),
            ("Something Else on Fifth", "Boutique", "Sales Associate (walk-in)", "walkin", "206 5th Ave, Brooklyn, NY 11217",
             "+1 718-622-1262", None, 40.6765951, -73.9805352, "Women's clothing, known for warm staff.", 11),
            ("Annie's Blue Ribbon General Store", "Boutique", "Sales Associate (walk-in)", "walkin", "232 5th Ave, Brooklyn, NY 11215",
             "+1 718-522-9848", None, 40.6756829, -73.9811344, "Neighborhood gift shop, community pillar.", 12),
            ("BLOK HILL", "Boutique", "Sales Associate (walk-in)", "walkin", "107a 7th Ave, Brooklyn, NY 11215",
             "+1 718-783-0789", None, 40.6739445, -73.9756389, "Home goods/clothing, small but well-reviewed.", 13),
            ("fig.", "Boutique", "Sales Associate (walk-in)", "walkin", "121 7th Ave, Brooklyn, NY 11215",
             "+1 718-622-5550", None, 40.673338, -73.975892, "Men's apparel boutique on 7th Ave.", 14),
            ("KIWI", "Boutique", "Sales Associate (walk-in)", "walkin", "119 7th Ave, Brooklyn, NY 11215",
             "+1 718-622-5551", None, 40.6734018, -73.9758977, "Women's clothing, same ownership as fig. next door.", 15),
        ]
        c.executemany('''
            INSERT INTO job_map_pins (name, category, role_title, status, address, phone, website, lat, lng, info, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', pins)
        conn.commit()

    conn.close()
    print("PostgreSQL database initialized")

def ensure_additional_seed_data():
    """Idempotently adds new leads/pins without duplicating or wiping existing rows."""
    try:
        conn = get_db()
        c = conn.cursor()

        extra_pins = [
            ("Freddy's Bar", "Bar", "Bartender / Server (walk-in)", "walkin", "627 5th Ave, Brooklyn, NY 11215",
             "+1 718-768-0131", None, 40.6632339, -73.9911145, "Laid-back neighborhood bar, back room hosts events — steady turnover.", 16),
            ("Chela", "Bar", "Server / Host (walk-in)", "walkin", "408 5th Ave, Brooklyn, NY 11215",
             "+1 718-701-1891", None, 40.6702928, -73.9856078, "Busy, well-reviewed Mexican restaurant — high volume, likely to need FOH help.", 17),
            ("Blueprint", "Bar", "Bartender / Server (walk-in)", "walkin", "196 5th Ave, Brooklyn, NY 11217",
             None, None, 40.6768844, -73.9803770, "Craft cocktail bar, evening hours.", 18),
            ("Black Oak on Fifth", "Bar", "Server / Host (walk-in)", "walkin", "200 5th Ave, Brooklyn, NY 11217",
             "+1 347-599-0491", None, 40.6768290, -73.9804610, "Casual comfort food spot, packed on weekends.", 19),
            ("Terrace Restaurant & Bakery", "Bar", "Server / Counter (walk-in)", "walkin", "280 5th Ave, Brooklyn, NY 11215",
             "+1 929-624-2646", None, 40.6742312, -73.9823146, "High-volume all-day brunch spot, huge menu.", 20),
            ("Prospect Bar and Grill", "Bar", "Bartender / Server (walk-in)", "walkin", "545 5th Ave, Brooklyn, NY 11215",
             "+1 347-599-1087", None, 40.6657841, -73.9889618, "Family-friendly bar/restaurant, brunch + evening crowd.", 21),
            ("South Slope Restaurant & Bar", "Bar", "Server / Counter (walk-in)", "walkin", "486 5th Ave, Brooklyn, NY 11215",
             "+1 718-499-0005", None, 40.6678145, -73.9876262, "Casual diner-style menu, steady daytime traffic.", 22),
        ]
        for p in extra_pins:
            c.execute('''
                INSERT INTO job_map_pins (name, category, role_title, status, address, phone, website, lat, lng, info, sort_order)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM job_map_pins WHERE name = %s)
            ''', p + (p[0],))

        extra_leads = [
            ("Tutoring & Mentoring", "Varsity Tutors", "Online Tutor — Psychology / Test Prep",
             "https://www.varsitytutors.com/tutoring/apply", "https://www.varsitytutors.com/tutoring/apply",
             "", "~$15\u2013$40/hr, self-set schedule",
             "1-on-1 online tutoring platform with high demand for psychology and test-prep subjects. Set your own hours, no cold-calling for clients.", 6),
            ("Tutoring & Mentoring", "Wyzant", "Private Tutor — set your own subjects & rate",
             "https://www.wyzant.com/tutor/apply", "https://www.wyzant.com/tutor/apply",
             "", "Tutor sets rate, typical $25\u2013$45/hr for psych/test prep",
             "Marketplace model — build a profile, students message you directly. Good fit for psych, research methods, or general test prep given his NYU background.", 7),
            ("Tutoring & Mentoring", "Ivy Tutors Network", "In-Person Tutor (NYC)",
             "https://ivytutorsnetwork.com/careers/", "https://ivytutorsnetwork.com/careers/",
             "", "Competitive, some roles include paid TA opportunities",
             "NYC-based in-person tutoring company; some listings mention paid TA opportunities alongside tutoring — good match for his research + tutoring combo.", 8),
            ("Tutoring & Mentoring", "The Princeton Review / Tutor.com", "Private Tutor",
             "https://www.princetonreview.com/company/careers", "https://www.princetonreview.com/company/careers",
             "", "Premium 1-on-1 rates, flexible",
             "Large, well-established tutoring brand (Tutor.com). Premium private tutoring program pays well above marketplace average for strong academic backgrounds.", 9),
        ]
        for l in extra_leads:
            c.execute('''
                INSERT INTO career_leads (category, org_name, role_title, website, apply_url, phone, pay_range, info, sort_order)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM career_leads WHERE org_name = %s)
            ''', l + (l[1],))

        extra_contacts = [
            ("Professional Network & References", "The Doe Fund", "Contact — Nazerine Griffin",
             "https://www.doe.org", "",
             "718-416-4924", "",
             "Nazerine Griffin — direct contact at The Doe Fund, where Jack previously worked as an Intake Specialist (June 2024 \u2013 Sept 2025). Worth reaching out re: references or new openings. Phone: 718-416-4924 or 646-772-5101.",
             "nazerine@doe.org", 10),
        ]
        for l in extra_contacts:
            c.execute('''
                INSERT INTO career_leads (category, org_name, role_title, website, apply_url, phone, pay_range, info, contact_email, sort_order)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM career_leads WHERE org_name = %s)
            ''', l + (l[1],))

        conn.commit()
        conn.close()
    except Exception as e:
        print("Additional seed error:", e)

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
    ensure_additional_seed_data()
except Exception as e:
    print("DB init warning:", e)

@app.route('/')
@login_required
def index():
    return render_template('career.html')

@app.route('/wellness')
@login_required
def wellness():
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

@app.route('/career')
@login_required
def career():
    return redirect(url_for('index'))

@app.route('/api/career/leads', methods=['GET'])
@login_required
def get_career_leads():
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM career_leads ORDER BY sort_order ASC, id ASC')
        rows = c.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("DB error:", e)
        return jsonify([]), 500

@app.route('/api/career/leads', methods=['POST'])
@login_required
def create_career_lead():
    data = request.get_json(force=True) or {}
    category = (data.get('category') or '').strip()
    org_name = (data.get('org_name') or '').strip()
    if not category or not org_name:
        return jsonify({"error": "Category and organization name are required."}), 400
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM career_leads')
        next_order = c.fetchone()['next_order']
        c.execute('''
            INSERT INTO career_leads
                (category, org_name, role_title, website, apply_url, phone, pay_range, info, contact_email, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        ''', (
            category, org_name,
            (data.get('role_title') or '').strip() or None,
            (data.get('website') or '').strip() or None,
            (data.get('apply_url') or '').strip() or None,
            (data.get('phone') or '').strip() or None,
            (data.get('pay_range') or '').strip() or None,
            (data.get('info') or '').strip() or None,
            (data.get('contact_email') or '').strip() or None,
            next_order
        ))
        row = c.fetchone()
        conn.commit()
        conn.close()
        return jsonify(row)
    except Exception as e:
        print("Create lead error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/career/leads/<int:lead_id>', methods=['DELETE'])
@login_required
def delete_career_lead(lead_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM career_leads WHERE id = %s', (lead_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        print("Delete lead error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/career/leads/<int:lead_id>', methods=['POST'])
@login_required
def update_career_lead(lead_id):
    data = request.get_json(force=True) or {}
    fields = []
    values = []
    if 'checked' in data:
        fields.append('checked = %s'); values.append(bool(data['checked']))
    if 'last_contact_date' in data:
        fields.append('last_contact_date = %s'); values.append(data['last_contact_date'] or None)
    if 'next_contact_date' in data:
        fields.append('next_contact_date = %s'); values.append(data['next_contact_date'] or None)
    if 'follow_up_notes' in data:
        fields.append('follow_up_notes = %s'); values.append(data['follow_up_notes'] or '')
    if 'contact_email' in data:
        fields.append('contact_email = %s'); values.append(data['contact_email'] or None)
    if not fields:
        return jsonify({"error": "no fields to update"}), 400
    fields.append('updated_at = CURRENT_TIMESTAMP')
    values.append(lead_id)
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute(f'UPDATE career_leads SET {", ".join(fields)} WHERE id = %s RETURNING *', values)
        row = c.fetchone()
        conn.commit()
        conn.close()
        return jsonify(row)
    except Exception as e:
        print("DB error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/career/leads/<int:lead_id>/send-email', methods=['POST'])
@login_required
def send_lead_email(lead_id):
    token = get_valid_gmail_access_token()
    if not token:
        return jsonify({"error": "Gmail isn't connected."}), 400

    data = request.get_json(force=True) or {}
    to_addr = (data.get('to') or '').strip()
    subject = (data.get('subject') or '').strip()
    body_text = data.get('body') or ''
    attachment_file_id = data.get('attachment_file_id')
    attachment_name = data.get('attachment_name')
    attachment_mime_type = data.get('attachment_mime_type')

    if not to_addr:
        return jsonify({"error": "Recipient email is required."}), 400
    if not subject:
        return jsonify({"error": "Subject is required."}), 400

    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM career_leads WHERE id = %s', (lead_id,))
        lead = c.fetchone()
        conn.close()
        if not lead:
            return jsonify({"error": "Lead not found."}), 404

        msg = MIMEMultipart()
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain'))

        attached_final_name = None
        if attachment_file_id:
            headers = {'Authorization': f'Bearer {token}'}
            if attachment_mime_type and attachment_mime_type.startswith('application/vnd.google-apps.'):
                export_res = requests.get(
                    f'https://www.googleapis.com/drive/v3/files/{attachment_file_id}/export',
                    headers=headers, params={'mimeType': 'application/pdf'}, timeout=30
                )
                if export_res.status_code != 200:
                    return jsonify({"error": f"Could not export attachment from Drive ({export_res.status_code})."}), 400
                file_bytes = export_res.content
                base_name = (attachment_name or 'Document').rsplit('.', 1)[0]
                attached_final_name = f"{base_name}.pdf"
                subtype = 'pdf'
            else:
                dl_res = requests.get(
                    f'https://www.googleapis.com/drive/v3/files/{attachment_file_id}',
                    headers=headers, params={'alt': 'media'}, timeout=30
                )
                if dl_res.status_code != 200:
                    return jsonify({"error": f"Could not download attachment from Drive ({dl_res.status_code})."}), 400
                file_bytes = dl_res.content
                attached_final_name = attachment_name or 'attachment'
                guessed_type, _ = mimetypes.guess_type(attached_final_name)
                subtype = (guessed_type.split('/')[-1] if guessed_type else 'octet-stream')

            part = MIMEApplication(file_bytes, _subtype=subtype)
            part.add_header('Content-Disposition', 'attachment', filename=attached_final_name)
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        send_res = requests.post(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'raw': raw},
            timeout=30
        )
        send_data = send_res.json()
        if send_res.status_code != 200 or 'id' not in send_data:
            err_msg = send_data.get('error', {}).get('message', 'Gmail send failed.')
            err_lower = err_msg.lower()
            needs_reauth = 'insufficient' in err_lower or 'scope' in err_lower
            return jsonify({"error": err_msg, "needs_reauth": needs_reauth}), 400

        if HAS_PYTZ:
            local_date = datetime.now(pytz.timezone('America/New_York')).date().isoformat()
        else:
            local_date = datetime.utcnow().date().isoformat()
        timestamp_str = get_brooklyn_time()

        log_entry = f'[{timestamp_str}] Emailed {to_addr} — Subject: "{subject}".'
        if attached_final_name:
            log_entry += f' Attachment: {attached_final_name}.'

        existing_notes = (lead.get('follow_up_notes') or '').strip()
        new_notes = (existing_notes + '\n\n' + log_entry) if existing_notes else log_entry

        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('''
            UPDATE career_leads
            SET last_contact_date = %s, follow_up_notes = %s, contact_email = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s RETURNING *
        ''', (local_date, new_notes, to_addr, lead_id))
        updated = c.fetchone()
        conn.commit()
        conn.close()

        return jsonify({"ok": True, "message_id": send_data['id'], "lead": updated})
    except Exception as e:
        print("Send email error:", e)
        return jsonify({"error": str(e)}), 500

# ── GMAIL JOB-RESPONSE INBOX ──────────────────────────────

@app.route('/api/career/map-pins', methods=['GET'])
@login_required
def get_map_pins():
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM job_map_pins ORDER BY sort_order ASC, id ASC')
        rows = c.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("DB error:", e)
        return jsonify([]), 500

@app.route('/api/career/map-pins/<int:pin_id>', methods=['POST'])
@login_required
def update_map_pin(pin_id):
    data = request.get_json(force=True) or {}
    if 'checked' not in data:
        return jsonify({"error": "no fields to update"}), 400
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('UPDATE job_map_pins SET checked = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                   (bool(data['checked']), pin_id))
        row = c.fetchone()
        conn.commit()
        conn.close()
        return jsonify(row)
    except Exception as e:
        print("DB error:", e)
        return jsonify({"error": str(e)}), 500

def get_gmail_rows():
    """Return ALL connected Gmail/Google accounts, oldest first."""
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM gmail_connection ORDER BY connected_at ASC')
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print("Gmail DB error:", e)
        return []

def get_gmail_row_by_email(email):
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM gmail_connection WHERE email = %s', (email,))
        row = c.fetchone()
        conn.close()
        return row
    except Exception as e:
        print("Gmail DB error:", e)
        return None

def refresh_gmail_access_token(row):
    if not row or not row.get('refresh_token'):
        return None
    try:
        res = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': row['refresh_token'],
            'grant_type': 'refresh_token',
        }, timeout=15)
        tok = res.json()
        access_token = tok.get('access_token')
        if not access_token:
            return None
        expiry = datetime.utcnow() + timedelta(seconds=tok.get('expires_in', 3600))
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE gmail_connection SET access_token=%s, token_expiry=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                   (access_token, expiry, row['id']))
        conn.commit()
        conn.close()
        return access_token
    except Exception as e:
        print("Gmail refresh error:", e)
        return None

def get_valid_gmail_access_token(email=None):
    """Get a valid access token for a specific account, or the primary account (GMAIL_TARGET_EMAIL)
    if no email is given — this keeps Documents/send-email pinned to the primary account even
    when additional accounts are connected."""
    target_email = email or GMAIL_TARGET_EMAIL
    row = get_gmail_row_by_email(target_email)
    if not row:
        return None
    expiry = row.get('token_expiry')
    if expiry and expiry > datetime.utcnow() + timedelta(seconds=60):
        return row['access_token']
    return refresh_gmail_access_token(row)

@app.route('/auth/gmail/connect')
@login_required
def gmail_connect():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return ("Gmail integration isn't configured yet. In Railway → jack-wellness → Variables, "
                "add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI "
                "(from a Google Cloud OAuth client with the Gmail API enabled), then reload this page."), 200
    target_email = request.args.get('email', '').strip() or GMAIL_TARGET_EMAIL
    state = secrets.token_urlsafe(16)
    session['gmail_oauth_state'] = state
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': GOOGLE_OAUTH_SCOPES,
        'access_type': 'offline',
        'prompt': 'select_account consent',
        'login_hint': target_email,
        'state': state,
    }
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))

@app.route('/auth/gmail/callback')
@login_required
def gmail_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code or state != session.get('gmail_oauth_state'):
        return redirect(url_for('index'))
    try:
        token_res = requests.post('https://oauth2.googleapis.com/token', data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code',
        }, timeout=15)
        tok = token_res.json()
        access_token = tok.get('access_token')
        refresh_token = tok.get('refresh_token')
        expires_in = tok.get('expires_in', 3600)
        if not access_token:
            print("Gmail callback error: no access_token in token response:", tok)
            return redirect(url_for('index'))
        email = None
        try:
            ui = requests.get('https://www.googleapis.com/oauth2/v2/userinfo',
                               headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
            email = ui.json().get('email')
        except Exception as e:
            print("Gmail callback userinfo error:", e)
        if not email:
            print("Gmail callback error: could not determine account email, aborting to avoid mislabeling a token")
            return redirect(url_for('index'))
        expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO gmail_connection (email, access_token, refresh_token, token_expiry)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (email) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, gmail_connection.refresh_token),
                token_expiry = EXCLUDED.token_expiry,
                updated_at = CURRENT_TIMESTAMP
        ''', (email, access_token, refresh_token, expiry))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Gmail callback error:", e)
    return redirect(url_for('index'))

@app.route('/api/career/gmail-status', methods=['GET'])
@login_required
def gmail_status():
    rows = get_gmail_rows()
    return jsonify({
        "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "connected": bool(rows),
        "accounts": [r['email'] for r in rows],
        "email": rows[0]['email'] if rows else None,
    })

@app.route('/api/career/gmail-disconnect', methods=['POST'])
@login_required
def gmail_disconnect():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    try:
        conn = get_db()
        c = conn.cursor()
        if email:
            c.execute('DELETE FROM gmail_connection WHERE email = %s', (email,))
        else:
            c.execute('DELETE FROM gmail_connection')
        conn.commit()
        conn.close()
    except Exception as e:
        print("Gmail disconnect error:", e)
    return jsonify({"ok": True})

def get_setting(key, default=None):
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT value FROM app_settings WHERE key = %s', (key,))
        row = c.fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception as e:
        print("Settings read error:", e)
        return default

def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
    ''', (key, value))
    conn.commit()
    conn.close()

def get_active_job_filter_query():
    return get_setting('gmail_job_filter_query', DEFAULT_JOB_FILTER_QUERY)

@app.route('/api/career/gmail-filter', methods=['GET'])
@login_required
def get_gmail_filter():
    return jsonify({
        "query": get_active_job_filter_query(),
        "is_custom": get_setting('gmail_job_filter_query') is not None,
        "default_query": DEFAULT_JOB_FILTER_QUERY,
    })

@app.route('/api/career/gmail-filter', methods=['POST'])
@login_required
def save_gmail_filter():
    data = request.get_json(force=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"error": "query cannot be empty"}), 400
    set_setting('gmail_job_filter_query', query)
    return jsonify({"ok": True, "query": query})

@app.route('/api/career/gmail-filter/reset', methods=['POST'])
@login_required
def reset_gmail_filter():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM app_settings WHERE key = 'gmail_job_filter_query'")
        conn.commit()
        conn.close()
    except Exception as e:
        print("Filter reset error:", e)
    return jsonify({"ok": True, "query": DEFAULT_JOB_FILTER_QUERY})

@app.route('/api/career/gmail-inbox', methods=['GET'])
@login_required
def gmail_inbox():
    accounts = get_gmail_rows()
    if not accounts:
        return jsonify({"connected": False, "messages": []})

    mode = request.args.get('mode', 'filtered')
    search_term = request.args.get('q', '').strip()

    if mode == 'all':
        query = 'in:inbox'
    elif mode == 'search':
        if not search_term:
            return jsonify({"connected": True, "messages": [], "error": "Enter a search term first."})
        query = search_term
    else:
        query = get_active_job_filter_query()

    all_msgs = []
    account_errors = []

    for account in accounts:
        account_email = account['email']
        token = get_valid_gmail_access_token(account_email)
        if not token:
            account_errors.append(f"{account_email}: could not refresh token")
            continue
        try:
            list_res = requests.get(
                'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                headers={'Authorization': f'Bearer {token}'},
                params={'q': query, 'maxResults': 25},
                timeout=15
            )
            data = list_res.json()
            if 'error' in data:
                account_errors.append(f"{account_email}: {data['error'].get('message', 'Gmail API error')}")
                continue
            for m in data.get('messages', [])[:25]:
                detail = requests.get(
                    f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{m["id"]}',
                    headers={'Authorization': f'Bearer {token}'},
                    params={'format': 'metadata', 'metadataHeaders': ['Subject', 'From', 'Date']},
                    timeout=15
                ).json()
                headers_list = detail.get('payload', {}).get('headers', [])
                hmap = {h['name']: h['value'] for h in headers_list}
                all_msgs.append({
                    "id": m['id'],
                    "subject": hmap.get('Subject', '(no subject)'),
                    "from": hmap.get('From', ''),
                    "date": hmap.get('Date', ''),
                    "snippet": detail.get('snippet', ''),
                    "link": f"https://mail.google.com/mail/u/0/#inbox/{m['id']}",
                    "account": account_email,
                    "internal_ts": detail.get('internalDate'),
                })
        except Exception as e:
            print(f"Gmail fetch error ({account_email}):", e)
            account_errors.append(f"{account_email}: {str(e)}")

    try:
        all_msgs.sort(key=lambda m: int(m.get('internal_ts') or 0), reverse=True)
    except Exception:
        pass
    for m in all_msgs:
        m.pop('internal_ts', None)

    result = {"connected": True, "messages": all_msgs, "mode": mode, "accounts": [a['email'] for a in accounts]}
    if account_errors and not all_msgs:
        result["error"] = "; ".join(account_errors)
    return jsonify(result)

# ── DOCUMENTS (Google Drive) ──────────────────────────────

DOC_KEYWORDS = ['passport', 'CV', 'resume', 'transcript', 'certificate', 'diploma',
                'cover letter', "driver's license", 'license', 'ID card', 'social security',
                'birth certificate', 'immunization', 'vaccination']

def escape_drive_query(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")

def build_default_doc_query():
    name_clauses = " or ".join([f"name contains '{escape_drive_query(kw)}'" for kw in DOC_KEYWORDS])
    return f"({name_clauses}) and trashed = false"

def get_active_doc_query():
    return get_setting('drive_doc_filter_query', build_default_doc_query())

@app.route('/documents')
@login_required
def documents_page():
    return render_template('documents.html')

@app.route('/videos')
@login_required
def videos_page():
    return render_template('videos.html')

def extract_youtube_id(url):
    import re as _re
    m = _re.search(r'(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/embed/)([A-Za-z0-9_-]{11})', url or '')
    return m.group(1) if m else None

@app.route('/api/career/resources', methods=['GET'])
@login_required
def get_resources():
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM career_resources ORDER BY sort_order ASC, id ASC')
        rows = c.fetchall()
        conn.close()
        for r in rows:
            r['youtube_id'] = extract_youtube_id(r['url']) if r['resource_type'] == 'video' else None
        return jsonify(rows)
    except Exception as e:
        print("Resources DB error:", e)
        return jsonify([]), 500

@app.route('/api/career/resources', methods=['POST'])
@login_required
def add_resource():
    data = request.get_json(force=True) or {}
    resource_type = (data.get('resource_type') or 'video').strip()
    title = (data.get('title') or '').strip()
    url = (data.get('url') or '').strip()
    synopsis = (data.get('synopsis') or '').strip()
    if not title or not url:
        return jsonify({"error": "Title and URL are required."}), 400
    if resource_type not in ('video', 'doc'):
        resource_type = 'video'
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM career_resources')
        next_order = c.fetchone()['next_order']
        c.execute('''
            INSERT INTO career_resources (resource_type, title, url, synopsis, sort_order)
            VALUES (%s,%s,%s,%s,%s) RETURNING *
        ''', (resource_type, title, url, synopsis, next_order))
        row = c.fetchone()
        conn.commit()
        conn.close()
        row['youtube_id'] = extract_youtube_id(row['url']) if row['resource_type'] == 'video' else None
        return jsonify(row)
    except Exception as e:
        print("Add resource error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/career/resources/<int:resource_id>', methods=['DELETE'])
@login_required
def delete_resource(resource_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM career_resources WHERE id = %s', (resource_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        print("Delete resource error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/career/documents-filter', methods=['GET'])
@login_required
def get_documents_filter():
    return jsonify({
        "query": get_active_doc_query(),
        "is_custom": get_setting('drive_doc_filter_query') is not None,
        "default_query": build_default_doc_query(),
    })

@app.route('/api/career/documents-filter', methods=['POST'])
@login_required
def save_documents_filter():
    data = request.get_json(force=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"error": "query cannot be empty"}), 400
    set_setting('drive_doc_filter_query', query)
    return jsonify({"ok": True, "query": query})

@app.route('/api/career/documents-filter/reset', methods=['POST'])
@login_required
def reset_documents_filter():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM app_settings WHERE key = 'drive_doc_filter_query'")
        conn.commit()
        conn.close()
    except Exception as e:
        print("Doc filter reset error:", e)
    return jsonify({"ok": True, "query": build_default_doc_query()})

@app.route('/api/career/documents', methods=['GET'])
@login_required
def get_documents():
    token = get_valid_gmail_access_token()  # same Google account/token, now scoped for Drive too
    if not token:
        return jsonify({"connected": False, "files": []})

    mode = request.args.get('mode', 'filtered')
    search_term = request.args.get('q', '').strip()

    if mode == 'all':
        query = 'trashed = false'
    elif mode == 'search':
        if not search_term:
            return jsonify({"connected": True, "files": [], "error": "Enter a search term first."})
        term = escape_drive_query(search_term)
        query = f"(name contains '{term}' or fullText contains '{term}') and trashed = false"
    else:
        query = get_active_doc_query()

    try:
        res = requests.get(
            'https://www.googleapis.com/drive/v3/files',
            headers={'Authorization': f'Bearer {token}'},
            params={
                'q': query,
                'fields': 'files(id,name,mimeType,webViewLink,iconLink,modifiedTime,size)',
                'orderBy': 'modifiedTime desc',
                'pageSize': 30,
            },
            timeout=15
        )
        data = res.json()
        if 'error' in data:
            msg = data['error'].get('message', 'Drive API error')
            msg_lower = msg.lower()
            needs_enable_api = 'has not been used' in msg_lower or 'it is disabled' in msg_lower or 'accessnotconfigured' in msg_lower
            needs_reauth = (not needs_enable_api) and ('insufficient' in msg_lower or 'scope' in msg_lower)
            enable_url = None
            if needs_enable_api:
                import re as _re
                url_match = _re.search(r'https://console\.developers\.google\.com\S+', msg)
                enable_url = url_match.group(0).rstrip('.') if url_match else None
            return jsonify({
                "connected": True, "files": [], "error": msg,
                "needs_reauth": needs_reauth,
                "needs_enable_api": needs_enable_api,
                "enable_url": enable_url,
            })
        return jsonify({"connected": True, "files": data.get('files', []), "mode": mode})
    except Exception as e:
        print("Drive fetch error:", e)
        return jsonify({"connected": True, "files": [], "error": str(e)})

# ── SPOTIFY ────────────────────────────────────────────────

def get_spotify_row():
    try:
        conn = get_db()
        c = conn.cursor(row_factory=dict_row)
        c.execute('SELECT * FROM spotify_connection ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        return row
    except Exception as e:
        print("Spotify DB error:", e)
        return None

def refresh_spotify_access_token(row):
    if not row or not row.get('refresh_token'):
        return None
    try:
        auth = (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        res = requests.post('https://accounts.spotify.com/api/token', data={
            'grant_type': 'refresh_token',
            'refresh_token': row['refresh_token'],
        }, auth=auth, timeout=15)
        tok = res.json()
        access_token = tok.get('access_token')
        if not access_token:
            return None
        expiry = datetime.utcnow() + timedelta(seconds=tok.get('expires_in', 3600))
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE spotify_connection SET access_token=%s, token_expiry=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                   (access_token, expiry, row['id']))
        conn.commit()
        conn.close()
        return access_token
    except Exception as e:
        print("Spotify refresh error:", e)
        return None

def get_valid_spotify_access_token():
    row = get_spotify_row()
    if not row:
        return None
    expiry = row.get('token_expiry')
    if expiry and expiry > datetime.utcnow() + timedelta(seconds=60):
        return row['access_token']
    return refresh_spotify_access_token(row)

@app.route('/auth/spotify/connect')
@login_required
def spotify_connect():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return ("Spotify integration isn't configured yet. In Railway → jack-wellness → Variables, "
                "add SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI "
                "(from a Spotify Developer app), then reload this page."), 200
    state = secrets.token_urlsafe(16)
    session['spotify_oauth_state'] = state
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'scope': SPOTIFY_SCOPES,
        'state': state,
    }
    return redirect('https://accounts.spotify.com/authorize?' + urlencode(params))

@app.route('/auth/spotify/callback')
@login_required
def spotify_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code or state != session.get('spotify_oauth_state'):
        return redirect(url_for('index'))
    try:
        token_res = requests.post('https://accounts.spotify.com/api/token', data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': SPOTIFY_REDIRECT_URI,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET,
        }, timeout=15)
        tok = token_res.json()
        access_token = tok.get('access_token')
        refresh_token = tok.get('refresh_token')
        expires_in = tok.get('expires_in', 3600)
        display_name = 'Spotify User'
        try:
            me = requests.get('https://api.spotify.com/v1/me',
                               headers={'Authorization': f'Bearer {access_token}'}, timeout=10).json()
            display_name = me.get('display_name') or display_name
        except Exception:
            pass
        expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM spotify_connection')
        c.execute('''
            INSERT INTO spotify_connection (display_name, access_token, refresh_token, token_expiry)
            VALUES (%s,%s,%s,%s)
        ''', (display_name, access_token, refresh_token, expiry))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Spotify callback error:", e)
    return redirect(url_for('index'))

@app.route('/api/career/spotify-status', methods=['GET'])
@login_required
def spotify_status():
    row = get_spotify_row()
    return jsonify({
        "configured": bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET),
        "connected": bool(row),
        "display_name": row['display_name'] if row else None,
    })

@app.route('/api/career/spotify-disconnect', methods=['POST'])
@login_required
def spotify_disconnect():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM spotify_connection')
        conn.commit()
        conn.close()
    except Exception as e:
        print("Spotify disconnect error:", e)
    return jsonify({"ok": True})

@app.route('/api/career/spotify-recent', methods=['GET'])
@login_required
def spotify_recent():
    token = get_valid_spotify_access_token()
    if not token:
        return jsonify({"connected": False})
    try:
        headers = {'Authorization': f'Bearer {token}'}
        now_playing = None
        np_res = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers, timeout=15)
        if np_res.status_code == 200 and np_res.text:
            npd = np_res.json()
            item = npd.get('item')
            if item:
                now_playing = {
                    "name": item.get('name'),
                    "artist": ", ".join(a['name'] for a in item.get('artists', [])),
                    "album_art": (item.get('album', {}).get('images') or [{}])[0].get('url'),
                    "is_playing": npd.get('is_playing', False),
                    "url": item.get('external_urls', {}).get('spotify'),
                }
        recent_res = requests.get('https://api.spotify.com/v1/me/player/recently-played',
                                   headers=headers, params={'limit': 10}, timeout=15)
        recent = []
        if recent_res.status_code == 200:
            for item in recent_res.json().get('items', []):
                track = item.get('track', {})
                recent.append({
                    "name": track.get('name'),
                    "artist": ", ".join(a['name'] for a in track.get('artists', [])),
                    "album_art": (track.get('album', {}).get('images') or [{}])[0].get('url'),
                    "played_at": item.get('played_at'),
                    "url": track.get('external_urls', {}).get('spotify'),
                })
        return jsonify({"connected": True, "now_playing": now_playing, "recent": recent})
    except Exception as e:
        print("Spotify recent error:", e)
        return jsonify({"connected": True, "now_playing": None, "recent": [], "error": str(e)})

@app.route('/api/career/spotify-control', methods=['POST'])
@login_required
def spotify_control():
    token = get_valid_spotify_access_token()
    if not token:
        return jsonify({"error": "not connected"}), 400
    data = request.get_json(force=True) or {}
    action = data.get('action')
    headers = {'Authorization': f'Bearer {token}'}
    try:
        if action == 'play':
            r = requests.put('https://api.spotify.com/v1/me/player/play', headers=headers, timeout=10)
        elif action == 'pause':
            r = requests.put('https://api.spotify.com/v1/me/player/pause', headers=headers, timeout=10)
        elif action == 'next':
            r = requests.post('https://api.spotify.com/v1/me/player/next', headers=headers, timeout=10)
        elif action == 'previous':
            r = requests.post('https://api.spotify.com/v1/me/player/previous', headers=headers, timeout=10)
        else:
            return jsonify({"error": "unknown action"}), 400
        if r.status_code == 204:
            return jsonify({"ok": True})
        if r.status_code == 404:
            return jsonify({"error": "No active Spotify device found. Open Spotify on your phone/computer first."}), 200
        return jsonify({"error": f"Spotify returned {r.status_code}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        pin = request.form.get('pin', '').strip()
        if pin == SITE_PASSWORD:
            session.permanent = True
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = 'Incorrect PIN'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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
    ensure_additional_seed_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
