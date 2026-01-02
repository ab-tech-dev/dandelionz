#!/usr/bin/env python
"""
Test script to verify SMTP email configuration and connectivity
Run this on your VPS: python test_email.py
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce_api.settings')
sys.path.insert(0, str(Path(__file__).resolve().parent))
django.setup()

from django.conf import settings
from django.core.mail import send_mail
import smtplib

def test_smtp_connection():
    """Test SMTP connection directly"""
    print("=" * 60)
    print("TESTING SMTP CONNECTION")
    print("=" * 60)
    
    print(f"\nEmail Configuration:")
    print(f"  EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"  EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"  EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
    print(f"  EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
    print(f"  EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"  DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    print(f"  EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
    
    try:
        if settings.EMAIL_USE_SSL:
            connection = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
            print(f"\n✓ Successfully connected to SMTP server (SSL)")
        else:
            connection = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
            print(f"\n✓ Successfully connected to SMTP server (TLS)")
            
            if settings.EMAIL_USE_TLS:
                connection.starttls()
                print(f"✓ Successfully started TLS")
        
        # Try to login
        if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
            connection.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            print(f"✓ Successfully authenticated with credentials")
        
        connection.quit()
        print(f"\n✓ SMTP connection test PASSED!")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n✗ SMTP Authentication Error: {str(e)}")
        print(f"  Check your EMAIL_HOST_USER and EMAIL_HOST_PASSWORD")
        return False
    except smtplib.SMTPException as e:
        print(f"\n✗ SMTP Error: {str(e)}")
        return False
    except Exception as e:
        print(f"\n✗ Connection Error: {str(e)}")
        return False

def test_django_send_mail():
    """Test sending email via Django"""
    print("\n" + "=" * 60)
    print("TESTING DJANGO SEND_MAIL")
    print("=" * 60)
    
    test_email = "joshua4ability@gmail.com"
    
    try:
        result = send_mail(
            subject="Test Email from Dandelionz",
            message="This is a test email to verify SMTP configuration.",
            html_message="<p>This is a test email to verify SMTP configuration.</p>",
            from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
            recipient_list=[test_email],
            fail_silently=False,
        )
        print(f"\n✓ Django send_mail returned: {result}")
        if result == 1:
            print(f"✓ Email successfully sent!")
            return True
        else:
            print(f"✗ send_mail returned {result}, expected 1")
            return False
            
    except Exception as e:
        print(f"\n✗ Error sending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    smtp_ok = test_smtp_connection()
    print("\n")
    
    if smtp_ok:
        django_ok = test_django_send_mail()
        if django_ok:
            print("\n" + "=" * 60)
            print("✓ ALL TESTS PASSED - Email configuration is working!")
            print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ SMTP connection failed - Fix the email configuration")
        print("=" * 60)
