# utils.py

import frappe

def prevent_default_welcome_email(doc, method=None):
    """Prevent Frappe's default welcome email from being sent"""
    # This flag prevents the default welcome email
    frappe.flags.in_import = True

def send_custom_welcome_email(doc, method=None):
    """Send custom welcome email based on module profile"""
    # Reset the flag after user is created
    frappe.flags.in_import = False
    
    # Only send if user has a module profile
    if not doc.module_profile:
        return
    
    # Check if it's Anticipatory Action Profile
    if doc.module_profile == "Anticipatory Action Profile":
        send_anticipatory_action_welcome(doc)
    # Add more conditions for other profiles
    # elif doc.module_profile == "Other Profile":
    #     send_other_profile_welcome(doc)

def send_anticipatory_action_welcome(user_doc):
    """Send welcome email for Anticipatory Action users"""
    
    # Generate password reset link
    from frappe.utils import get_url
    
    if user_doc.reset_password_key:
        reset_password_link = get_url(f"/update-password?key={user_doc.reset_password_key}")
    else:
        # Generate a new reset key if it doesn't exist
        user_doc.reset_password_key = frappe.generate_hash(length=32)
        user_doc.save(ignore_permissions=True)
        reset_password_link = get_url(f"/update-password?key={user_doc.reset_password_key}")
    
    # Send the email
    frappe.sendmail(
        recipients=[user_doc.email],
        subject="Welcome to Anticipatory Action!",
        template="anticipatory_action_welcome",  # Your email template name
        args={
            "first_name": user_doc.first_name,
            "full_name": user_doc.full_name,
            "reset_password_link": reset_password_link,
            "user_email": user_doc.email
        },
        now=True
    )