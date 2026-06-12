import os
import resend
from datetime import datetime

resend.api_key = os.getenv("RESEND_API_KEY")


def send_welcome_email(name: str, email: str):
    # If no API key is configured, skip gracefully instead of crashing the
    # (background) signup task. The user is still created and logged in.
    if not resend.api_key:
        print("⚠️  RESEND_API_KEY not set — skipping welcome email")
        return

    first_name = name.split()[0] if name.split() else name
    year = datetime.now().year

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to Veriify</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #F0F4FF;
    padding: 40px 20px;
  }}

  .container {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(79, 70, 229, 0.15);
  }}

  .hero {{
    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 50%, #06B6D4 100%);
    padding: 60px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
  }}

  .hero::before {{
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
    animation: pulse 4s ease-in-out infinite;
  }}

  .logo {{
    font-size: 42px;
    font-weight: 700;
    color: white;
    letter-spacing: -1px;
    margin-bottom: 8px;
  }}

  .tagline {{
    color: rgba(255,255,255,0.85);
    font-size: 14px;
    letter-spacing: 3px;
    text-transform: uppercase;
    font-weight: 500;
  }}

  .hero-badge {{
    display: inline-block;
    background: rgba(255,255,255,0.2);
    border: 1px solid rgba(255,255,255,0.3);
    color: white;
    padding: 6px 16px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-top: 20px;
  }}

  .body {{
    padding: 48px 40px;
  }}

  .greeting {{
    font-size: 28px;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 16px;
    line-height: 1.3;
  }}

  .greeting span {{
    background: linear-gradient(135deg, #4F46E5, #06B6D4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}

  .intro {{
    color: #475569;
    font-size: 16px;
    line-height: 1.7;
    margin-bottom: 32px;
  }}

  .features {{
    background: #F8FAFF;
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 32px;
    border: 1px solid #E8EEFF;
  }}

  .features-title {{
    font-size: 13px;
    font-weight: 600;
    color: #4F46E5;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 20px;
  }}

  .feature {{
    display: flex;
    align-items: flex-start;
    margin-bottom: 16px;
    gap: 12px;
  }}

  .feature:last-child {{ margin-bottom: 0; }}

  .feature-icon {{
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }}

  .feature-icon.blue {{ background: #EEF2FF; }}
  .feature-icon.purple {{ background: #F5F3FF; }}
  .feature-icon.cyan {{ background: #ECFEFF; }}

  .feature-text h4 {{
    font-size: 14px;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 2px;
  }}

  .feature-text p {{
    font-size: 13px;
    color: #64748B;
    line-height: 1.5;
  }}

  .cta {{
    text-align: center;
    margin-bottom: 32px;
  }}

  .cta-button {{
    display: inline-block;
    background: linear-gradient(135deg, #4F46E5, #7C3AED);
    color: white !important;
    text-decoration: none;
    padding: 16px 48px;
    border-radius: 100px;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.5px;
    box-shadow: 0 8px 24px rgba(79, 70, 229, 0.35);
  }}

  .cta-sub {{
    margin-top: 12px;
    font-size: 13px;
    color: #94A3B8;
  }}

  .quote {{
    border-left: 3px solid #4F46E5;
    padding: 16px 20px;
    background: #F8FAFF;
    border-radius: 0 12px 12px 0;
    margin-bottom: 32px;
  }}

  .quote p {{
    font-size: 15px;
    color: #334155;
    font-style: italic;
    line-height: 1.6;
  }}

  .quote cite {{
    font-size: 12px;
    color: #94A3B8;
    font-style: normal;
    margin-top: 8px;
    display: block;
  }}

  .footer {{
    background: #F8FAFF;
    padding: 28px 40px;
    text-align: center;
    border-top: 1px solid #E8EEFF;
  }}

  .footer p {{
    font-size: 12px;
    color: #94A3B8;
    line-height: 1.6;
  }}

  .footer .brand {{
    font-weight: 600;
    color: #4F46E5;
  }}

  .stats {{
    display: flex;
    justify-content: center;
    gap: 32px;
    margin-bottom: 32px;
    text-align: center;
  }}

  .stat-number {{
    font-size: 24px;
    font-weight: 700;
    color: #4F46E5;
    display: block;
  }}

  .stat-label {{
    font-size: 11px;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 500;
  }}

  @keyframes pulse {{
    0%, 100% {{ transform: scale(1); opacity: 0.6; }}
    50% {{ transform: scale(1.1); opacity: 1; }}
  }}
</style>
</head>
<body>
<div class="container">
  <!-- Hero -->
  <div class="hero">
    <div class="logo">Veriify</div>
    <div class="tagline">Walk In Nervous. Walk Out Ready.</div>
    <div class="hero-badge">✦ Beta Access Granted</div>
  </div>

  <!-- Body -->
  <div class="body">
    <h1 class="greeting">
      Welcome aboard,<br>
      <span>{first_name}.</span>
    </h1>

    <p class="intro">
      You're now part of a select group of beta testers shaping the
      future of interview preparation. Veriify uses cutting-edge AI
      to simulate real interviews — so when the real moment comes,
      you're already ready.
    </p>

    <!-- Stats -->
    <div class="stats">
      <div>
        <span class="stat-number">500+</span>
        <span class="stat-label">Roles Covered</span>
      </div>
      <div>
        <span class="stat-number">10x</span>
        <span class="stat-label">More Confident</span>
      </div>
      <div>
        <span class="stat-number">100%</span>
        <span class="stat-label">Private &amp; Local</span>
      </div>
    </div>

    <!-- Features -->
    <div class="features">
      <div class="features-title">What's waiting for you</div>

      <div class="feature">
        <div class="feature-icon blue">🎯</div>
        <div class="feature-text">
          <h4>AI Interviewer That Adapts</h4>
          <p>Every question is tailored to your resume and the
             job description — no generic questions.</p>
        </div>
      </div>

      <div class="feature">
        <div class="feature-icon purple">🎙️</div>
        <div class="feature-text">
          <h4>Full Voice Mode</h4>
          <p>Practice speaking your answers out loud —
             just like a real interview call.</p>
        </div>
      </div>

      <div class="feature">
        <div class="feature-icon cyan">📊</div>
        <div class="feature-text">
          <h4>Brutally Honest Feedback</h4>
          <p>Detailed scores, ideal answers, and specific
             action items — not generic encouragement.</p>
        </div>
      </div>
    </div>

    <!-- CTA -->
    <div class="cta">
      <a href="http://localhost:8000" class="cta-button">
        Open Veriify →
      </a>
      <p class="cta-sub">Already installed on your computer</p>
    </div>

    <!-- Quote -->
    <div class="quote">
      <p>"The secret of getting ahead is getting started.
          Your next interview just got a lot less scary."</p>
      <cite>— The Veriify Team</cite>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>
      You're receiving this because you signed up for
      <span class="brand">Veriify</span> beta access.<br>
      © {year} Veriify. Built with ❤️ for job seekers everywhere.
    </p>
  </div>
</div>
</body>
</html>
"""

    try:
        resend.Emails.send({
            "from": "Veriify <onboarding@resend.dev>",
            "to": email,
            "subject": f"Welcome to Veriify, {first_name} 🎯",
            "html": html,
        })
        print(f"✅ Welcome email sent to {email}")
    except Exception as e:
        print(f"⚠️  Welcome email failed for {email}: {e}")
