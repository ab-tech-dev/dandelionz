"""
Custom email backend with connection pooling and retry logic
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
    - Connection pooling
    - Automatic retry on connection failures
    - Proper timeout handling
    - Better error logging
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = getattr(settings, 'EMAIL_CONNECTION_RETRY_ATTEMPTS', 3)
        self.retry_delay = getattr(settings, 'EMAIL_CONNECTION_RETRY_DELAY', 2)
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 30)

    def open(self):
        """
        Open SMTP connection with retry logic
        """
        if self.connection is not None:
            return False

        for attempt in range(self.max_retries):
            try:
                self.connection = self.connection_class(
                    self.host,
                    self.port,
                    local_hostname=getattr(settings, 'EMAIL_LOCAL_HOSTNAME', None),
                    timeout=self.timeout,
                )
                
                if self.use_tls:
                    self.connection.starttls()
                if self.use_ssl:
                    # If use_ssl is True, connection_class will be SMTP_SSL,
                    # and starttls should not be called
                    pass
                    
                if self.username and self.password:
                    self.connection.login(self.username, self.password)
                
                logger.info(f"SMTP connection established successfully on attempt {attempt + 1}")
                return True
                
            except smtplib.SMTPConnectionError as e:
                logger.warning(
                    f"SMTP connection error on attempt {attempt + 1}/{self.max_retries}: {str(e)}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to establish SMTP connection after {self.max_retries} attempts")
                    raise
                    
            except smtplib.SMTPException as e:
                logger.error(f"SMTP error during connection: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise
                    
            except OSError as e:
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{self.max_retries}: {str(e)}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to connect to SMTP server after {self.max_retries} attempts")
                    raise
                    
        return False

    def send_messages(self, email_messages):
        """
        Send messages with connection handling and retry logic
        """
        if not email_messages:
            return 0

        msg_count = 0
        retry_count = 0
        max_retries = 2

        while retry_count < max_retries:
            try:
                new_conn_created = self.open()
                if not self.connection:
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        logger.error("Could not establish SMTP connection for sending messages")
                        return 0

                for message in email_messages:
                    try:
                        sent = self._send(message)
                        if sent:
                            msg_count += 1
                    except (smtplib.SMTPServerDisconnected, OSError, TimeoutError) as e:
                        logger.error(f"Connection error sending message to {message.to}: {str(e)}")
                        # Close connection on SMTP error and retry
                        self.close()
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(self.retry_delay * 2)  # Longer delay for network errors
                            break
                        else:
                            raise
                    except smtplib.SMTPException as e:
                        logger.error(f"SMTP error sending message to {message.to}: {str(e)}")
                        # Close connection on SMTP error and retry
                        self.close()
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(self.retry_delay)
                            break
                        else:
                            raise
                    except Exception as e:
                        logger.error(f"Error sending message to {message.to}: {str(e)}")
                        raise

                # Successfully sent all messages
                if new_conn_created:
                    self.close()
                return msg_count

            except Exception as e:
                logger.error(f"Error in send_messages (attempt {retry_count + 1}): {str(e)}")
                self.close()
                if retry_count < max_retries - 1:
                    retry_count += 1
                    time.sleep(self.retry_delay)
                else:
                    raise

        return msg_count

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
