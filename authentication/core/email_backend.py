"""
Custom email backend with better logging
"""
import logging
import smtplib
import time
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend

logger = logging.getLogger(__name__)


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
