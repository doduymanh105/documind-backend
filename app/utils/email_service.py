import resend
import os
from dotenv import load_dotenv

load_dotenv()
resend.api_key = os.getenv("RESEND_API_KEY")

async def send_verification_otp(email_to: str, otp: str):
    try:
        # 1. Chuẩn bị nội dung HTML
        html_content = f"""
        <div style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 400px; margin: auto; background: white; padding: 30px; border-radius: 10px; text-align: center;">
                <h2 style="color: #333;">Verify DocuMind's Account</h2>
                <p style="color: #666;">Your verification code is:</p>
                <div style="font-size: 32px; font-weight: bold; color: #4A90E2; letter-spacing: 5px; margin: 20px 0; padding: 10px; border: 2px dashed #4A90E2;">
                    {otp}
                </div>
                <p style="font-size: 12px; color: #999;">This code is valid for 10 minutes. Please do not share it with anyone.</p>
            </div>
        </div>
        """

        # 2. Tạo dictionary đúng cấu trúc của Resend
        resend_from = os.getenv("RESEND_FROM_EMAIL", "DocuMind <onboarding@resend.dev>")
        params = {
            "from": resend_from,
            "to": [email_to],      
            "subject": "[DocuMind] Verification Code",
            "html": html_content
        }

     
        r = resend.Emails.send(params)
        print(f"Mail sent successfully to {email_to}")
        return r

    except Exception as e:
        print(f"Error sending email: {e}")
        return None