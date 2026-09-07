from html import escape


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;background:#f4f6f8;font-family:Arial,sans-serif;color:#17202a;">
    <div style="max-width:620px;margin:32px auto;background:#ffffff;border:1px solid #dfe4ea;">
            <div style="padding:22px 28px;background:#123b5d;color:#ffffff;">
                <div style="font-size:13px;letter-spacing:1px;">ARASPL</div>
                <h1 style="margin:8px 0 0;font-size:22px;">{escape(title)}</h1>
      </div>
      <div style="padding:28px;line-height:1.6;">{body}</div>
      <div style="padding:16px 28px;border-top:1px solid #e9edf1;color:#6b7785;font-size:12px;">
        Araspl Steels Private Limited | Steel, fabrication, logistics and safety
      </div>
    </div>
  </body>
</html>"""


def company_profile(name: str = "") -> tuple[str, str]:
    subject = "Araspl Steels Private Limited | Company Profile"
    greeting = f"<p>Dear {escape(name)},</p>" if name else "<p>Dear Sir/Madam,</p>"
    body = (
        greeting
        +
        "<h2 style=\"color:#123b5d;margin:22px 0 8px;\">About Araspl Steels Private Limited</h2>"
        "<p>What creates a nation's tomorrow? A great vision, futuristic infrastructure, and products built with strength and durability.</p>"
        "<p>At Araspl Steels Private Limited (RASPL), we bring these qualities together. RASPL is a leading name in the steel industry, with capabilities across fabrication, logistics, and safety. We provide top-quality products and execute promising projects for India's most reputed brands.</p>"
        "<p>We began our journey as a modest single-product business and have grown into a diversified enterprise with a presence across PAN India and neighbouring countries. Our expertise spans structural steels, fabricated steel structures, allied products, and related services.</p>"
        "<h2 style=\"color:#123b5d;margin:22px 0 8px;\">Our Service Categories</h2>"
        "<ul style=\"padding-left:20px;\">"
        "<li><strong>Supplies:</strong> Industrial supplies tested for strength, durability, and quality.</li>"
        "<li><strong>Fabrication:</strong> Fabricated steel structures and project execution.</li>"
        "<li><strong>Logistics:</strong> Reliable movement and delivery support across our operating regions.</li>"
        "<li><strong>Safety:</strong> Safety-focused products and practices for industrial requirements.</li>"
        "</ul>"
        "<h2 style=\"color:#123b5d;margin:22px 0 8px;\">Products and Solutions</h2>"
        "<p>Our product range includes MS steel, aluminium steel, stainless steel, roofing sheets, alloy steel, cement, pipes and fittings, hardware, structural steel, fabricated steel structures, and other allied products.</p>"
        "<p>Our supplies are produced with quality materials and current technology, and are checked by quality controllers against relevant quality parameters before delivery.</p>"
        "<p>We look forward to understanding your requirements and exploring how RASPL can support your upcoming projects.</p>"
        "<p>For more information, visit <a href=\"http://www.raspl.co.in/aboutus.php\" style=\"color:#123b5d;font-weight:bold;\">www.raspl.co.in</a>.</p>"
    )
    return subject, _layout(subject, body)


TEMPLATES = {
    "company_profile": company_profile,
}


def render_template(template_name: str, name: str) -> tuple[str, str]:
    try:
        template = TEMPLATES[template_name.lower()]
    except KeyError as error:
        choices = ", ".join(sorted(TEMPLATES))
        raise ValueError(f"Unknown template '{template_name}'. Choose: {choices}") from error
    return template(name)