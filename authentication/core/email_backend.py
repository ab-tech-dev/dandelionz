"""
Custom email backend with better logging
"""
import logging
import smtplib
import time
import re
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend

logger = logging.getLogger(__name__)

# Simple email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class RobustSMTPEmailBackend(DjangoEmailBackend):
    """
    Custom SMTP email backend with:
    - Better logging for debugging
    - Timeout handling
    - Proper error reporting
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 30)

    def open(self):
        """
        Open SMTP connection with better error logging
        """
        if self.connection is not None:
            return False
        
        try:
            logger.info(f"Attempting to open SMTP connection to {self.host}:{self.port}")
            logger.info(f"  EMAIL_USE_TLS: {self.use_tls}, EMAIL_USE_SSL: {self.use_ssl}")
            
            self.connection = self.connection_class(
                self.host,
                self.port,
                timeout=self.timeout,
            )
            
            if self.use_tls:
                logger.info("Starting TLS...")
                self.connection.starttls()
                
            if self.username and self.password:
                logger.info(f"Authenticating as {self.username}...")
                self.connection.login(self.username, self.password)
            
            logger.info("SMTP connection established and authenticated successfully")
            return True
                
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication Error: {str(e)}")
            logger.error("Check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in settings")
            self.connection = None
            raise
                    
        except smtplib.SMTPException as e:
            logger.error(f"SMTP Error: {str(e)}")
            self.connection = None
            raise
                    
        except OSError as e:
            logger.error(f"Network/Connection Error: {str(e)}")
            self.connection = None
            raise
        
        except Exception as e:
            logger.error(f"Unexpected error opening SMTP connection: {str(e)}")
            self.connection = None
            raise

    def send_messages(self, email_messages):
        """
        Send messages using parent Django implementation with logging
        """
        if not email_messages:
            logger.warning("send_messages called with empty email_messages list")
            return 0

        # Validate all recipient emails before sending
        invalid_emails = []
        for message in email_messages:
            for recipient in message.to:
                if not self._is_valid_email(recipient):
                    invalid_emails.append(recipient)
                    logger.error(f"Invalid email address detected: '{recipient}' - skipping this message")

        if invalid_emails:
            # Filter out messages with invalid recipients
            valid_messages = [
                msg for msg in email_messages
                if not any(not self._is_valid_email(r) for r in msg.to)
            ]
            
            if not valid_messages:
                logger.error(f"All messages contain invalid email addresses. Aborting send operation.")
                logger.error(f"Invalid emails: {invalid_emails}")
                raise ValueError(f"No valid recipients found. Invalid emails: {', '.join(invalid_emails)}")
            
            logger.warning(f"Filtered out {len(email_messages) - len(valid_messages)} messages with invalid emails")
            email_messages = valid_messages

        logger.info(f"Attempting to send {len(email_messages)} message(s)")
        msg_count = 0
        
        try:
            msg_count = super().send_messages(email_messages)
            logger.info(f"Successfully sent {msg_count} out of {len(email_messages)} messages")
            return msg_count
            
        except Exception as e:
            logger.error(f"Error sending messages: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    @staticmethod
    def _is_valid_email(email):
        """
        Validate email format using regex.
        Returns True if email matches standard format, False otherwise.
        """
        if not email or not isinstance(email, str):
            return False
        
        email = email.strip()
        
        # Check basic format
        if not EMAIL_REGEX.match(email):
            return False
        
        # Ensure it has both local and domain parts
        if '@' not in email:
            return False
        
        local_part, domain = email.rsplit('@', 1)
        
        # Local part should not be empty
        if not local_part:
            return False
        
        # Domain should have at least one dot
        if '.' not in domain:
            return False
        
        # Domain parts should not be empty
        parts = domain.split('.')
        if any(not part for part in parts):
            return False
        
        return True

    def close(self):
        """Close SMTP connection with error handling"""
        try:
            if self.connection is None:
                return
            try:
                self.connection.quit()
            except (smtplib.SMTPServerDisconnected, AttributeError):
                # This happens when calling quit() on a TLS connection
                # sometimes, or when the connection was already disconnected
                # by the server.
                self.connection.close()
            except smtplib.SMTPException as e:
                logger.warning(f"SMTP error during close: {str(e)}")
                self.connection.close()
            finally:
                self.connection = None
        except Exception as e:
            logger.error(f"Error closing SMTP connection: {str(e)}")
