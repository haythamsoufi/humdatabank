import base64
import requests
from typing import Iterable, Optional, List, Tuple
from flask import current_app
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def _to_list(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def _filter_recipients_for_environment(recipients: List[str], cc: List[str], bcc: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    Filter email recipients based on ALLOWED_EMAIL_RECIPIENTS_DEV.

    When ALLOWED_EMAIL_RECIPIENTS_DEV is set (comma-separated list), only those addresses
    receive emails. All others are filtered out. Use in dev/staging to avoid sending to real users.
    """
    allowed = current_app.config.get("ALLOWED_EMAIL_RECIPIENTS_DEV") or []
    if not allowed:
        return recipients, cc, bcc

    allowed_set = {e.strip().lower() for e in allowed if e and str(e).strip()}
    if not allowed_set:
        return recipients, cc, bcc

    def _filter(lst: List[str]) -> List[str]:
        return [e for e in lst if str(e).strip().lower() in allowed_set]

    return _filter(recipients), _filter(cc), _filter(bcc)


def send_email(
    subject: str,
    recipients: Iterable[str],
    html: str,
    sender: Optional[str] = None,
    text: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    importance: Optional[str] = None,
    attachments: Optional[List[Tuple[str, bytes, str]]] = None,
    _filtered_out: Optional[list] = None,
) -> bool:
    """
    Send an email using the Email API.

    Args:
        subject: Email subject line
        recipients: List of recipient email addresses (To field)
        html: HTML email content
        sender: Sender email address (optional, uses MAIL_DEFAULT_SENDER if not provided)
        text: Plain text email content (optional)
        reply_to: Reply-to email address (optional)
        cc: List of CC email addresses (optional)
        bcc: List of BCC email addresses (optional)
        importance: Email importance level ('high', 'normal', 'low'). If 'high', adds [HIGH PRIORITY] prefix to subject.
        attachments: Optional list of (filename, content_bytes, content_type) to attach.

    Returns:
        True if email was sent successfully, False otherwise
    """
    sender_email = sender or current_app.config.get("MAIL_DEFAULT_SENDER")
    recipients_list = _to_list(recipients)
    cc_list = _to_list(cc)
    bcc_list = _to_list(bcc)

    if not recipients_list and not cc_list and not bcc_list:
        current_app.logger.warning("send_email called with no recipients")
        return False

    # Validate sender email is configured
    if not sender_email:
        current_app.logger.error(
            "MAIL_DEFAULT_SENDER is not configured. "
            "Please set MAIL_DEFAULT_SENDER in your environment variables."
        )
        return False

    # Apply recipient filtering (e.g. ALLOWED_EMAIL_RECIPIENTS_DEV in dev)
    recipients_list, cc_list, bcc_list = _filter_recipients_for_environment(recipients_list, cc_list, bcc_list)

    # If all recipients were filtered out, skip send and signal to caller
    if not recipients_list and not cc_list and not bcc_list:
        if _filtered_out is not None:
            _filtered_out.append(True)
        return False

    # Add priority prefix to subject when high or urgent
    final_subject = subject
    if importance == 'urgent':
        if not subject.startswith('[URGENT]'):
            final_subject = f"[URGENT] {subject}"
    elif importance == 'high':
        if not subject.startswith('[HIGH PRIORITY]'):
            final_subject = f"[HIGH PRIORITY] {subject}"

    return _send_via_ifrc(
        subject=final_subject,
        sender=sender_email,
        recipients=recipients_list,
        html=html,
        text=text,
        reply_to=reply_to,
        cc=cc_list,
        bcc=bcc_list,
    )


def _send_via_ifrc(
    subject: str,
    sender: str,
    recipients: List[str],
    html: str,
    text: Optional[str],
    reply_to: Optional[str],
    cc: List[str],
    bcc: List[str],
    attachments: Optional[List[Tuple[str, bytes, str]]] = None,
) -> bool:
    """
    Send email via IFRC Email API.

    Uses base64-encoded fields matching the API format:
    - Fixed "To" address (no-reply@example.com)
    - Actual recipients go in To/CC/BCC based on parameters
    - All fields are base64 encoded
    """
    api_key = current_app.config.get("EMAIL_API_KEY")
    api_url_base = current_app.config.get("EMAIL_API_URL", "")

    if not api_key:
        current_app.logger.error(
            "Missing EMAIL_API_KEY for Email API. "
            "Please configure EMAIL_API_KEY or environment-specific key (EMAIL_API_KEY_PROD/STG) in your environment."
        )
        return False
    if not api_url_base:
        current_app.logger.error(
            "Missing EMAIL_API_URL configuration. "
            "Please set EMAIL_API_URL_PROD or EMAIL_API_URL_STG based on your environment."
        )
        return False

    # Check if API key is already in URL
    parsed_url = urlparse(api_url_base)
    query_params = parse_qs(parsed_url.query)

    if 'apiKey' in query_params or 'apikey' in query_params:
        api_url = api_url_base
        api_key_in_url = True
    else:
        # Add API key to URL query parameter
        new_query = urlencode(query_params, doseq=True) if query_params else ''
        api_url = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        api_key_in_url = False

    # Prepare request payload - IFRC Email API uses base64-encoded fields.
    # The "To" field is a required dummy address in the API payload; actual
    # recipients are delivered via To/CC/BCC fields below. Use the configured
    # noreply sender so the envelope looks coherent rather than example.com.
    fixed_to_address = current_app.config.get("MAIL_NOREPLY_SENDER") or sender

    # Convert recipients to comma-separated strings for encoding
    recipients_string = ",".join(recipients) if recipients else ""
    cc_string = ",".join(cc) if cc else ""
    bcc_string = ",".join(bcc) if bcc else ""

    # Calculate total recipients for logging
    all_recipients = recipients.copy()
    if cc:
        all_recipients.extend(cc)
    if bcc:
        all_recipients.extend(bcc)

    # Build payload with base64-encoded fields
    # Note: IFRC Email API uses fixed To address, actual recipients go in CC/BCC
    payload = {
        "FromAsBase64": str(base64.b64encode(sender.encode("utf-8")), "utf-8"),
        "ToAsBase64": str(base64.b64encode(fixed_to_address.encode("utf-8")), "utf-8"),
        "CcAsBase64": str(base64.b64encode(cc_string.encode("utf-8")), "utf-8") if cc_string else "",
        "BccAsBase64": str(base64.b64encode(bcc_string.encode("utf-8")), "utf-8") if bcc_string else "",
        "SubjectAsBase64": str(base64.b64encode(subject.encode("utf-8")), "utf-8"),
        "BodyAsBase64": str(base64.b64encode(html.strip().encode("utf-8")), "utf-8"),
        "IsBodyHtml": True,
        "TemplateName": "",
        "TemplateLanguage": "",
    }
    # Add attachments if supported by the API (optional; API may use AttachmentsAsBase64 or similar)
    if attachments:
        try:
            payload["Attachments"] = [
                {
                    "FileNameAsBase64": str(base64.b64encode((fn or "attachment").encode("utf-8")), "utf-8"),
                    "ContentAsBase64": str(base64.b64encode(content), "utf-8"),
                    "ContentType": (ct or "application/octet-stream"),
                }
                for fn, content, ct in attachments
            ]
        except Exception as e:
            current_app.logger.warning(f"Email attachments skipped (API may not support them): {e}")

    # Legacy behavior: If we have To recipients but no CC/BCC, combine To recipients with CC/BCC in BCC
    # This maintains backward compatibility with existing code
    if recipients_string and not cc_string and not bcc_string:
        # Single recipient: use To field directly
        if len(recipients) == 1:
            payload["ToAsBase64"] = str(base64.b64encode(recipients[0].encode("utf-8")), "utf-8")
            payload["BccAsBase64"] = ""
        else:
            # Multiple recipients: put in BCC (legacy behavior)
            payload["BccAsBase64"] = str(base64.b64encode(recipients_string.encode("utf-8")), "utf-8")
    elif recipients_string:
        # We have To recipients along with CC/BCC - combine To with BCC for legacy compatibility
        # But also set CC if provided
        combined_bcc = recipients.copy()
        if bcc:
            combined_bcc.extend(bcc)
        bcc_combined_string = ",".join(combined_bcc)
        payload["BccAsBase64"] = str(base64.b64encode(bcc_combined_string.encode("utf-8")), "utf-8")
        if cc_string:
            payload["CcAsBase64"] = str(base64.b64encode(cc_string.encode("utf-8")), "utf-8")

    try:
        headers = {"Content-Type": "application/json"}

        # Add API key to URL if not already present
        if api_key_in_url:
            resp = requests.post(api_url, headers=headers, json=payload, timeout=15)
        else:
            parsed_url_with_key = urlparse(api_url)
            query_params_with_key = parse_qs(parsed_url_with_key.query)
            query_params_with_key['apiKey'] = [api_key]
            new_query_with_key = urlencode(query_params_with_key, doseq=True)
            api_url_with_key = urlunparse((
                parsed_url_with_key.scheme,
                parsed_url_with_key.netloc,
                parsed_url_with_key.path,
                parsed_url_with_key.params,
                new_query_with_key,
                parsed_url_with_key.fragment
            ))
            resp = requests.post(api_url_with_key, headers=headers, json=payload, timeout=15)

        if 200 <= resp.status_code < 300:
            guid = resp.text.replace('"', '').strip() if resp.text else None
            total_recipients = len(recipients) + len(cc) + len(bcc)
            if guid:
                current_app.logger.info(
                    f"Email sent successfully via Email API to {total_recipients} recipient(s) "
                    f"(To: {len(recipients)}, CC: {len(cc)}, BCC: {len(bcc)}). GUID: {guid}"
                )
            else:
                current_app.logger.info(
                    f"Email sent successfully via Email API to {total_recipients} recipient(s) "
                    f"(To: {len(recipients)}, CC: {len(cc)}, BCC: {len(bcc)})"
                )
            return True

        # Error logging
        parsed_base = urlparse(api_url_base)
        safe_url = urlunparse((
            parsed_base.scheme,
            parsed_base.netloc,
            parsed_base.path,
            parsed_base.params,
            '',
            parsed_base.fragment
        ))

        error_message = resp.text[:200] if resp.text else 'No response body'
        if resp.status_code == 401:
            current_app.logger.error(
                f"Email API authentication failed (401) for {safe_url}. "
                f"Verify EMAIL_API_KEY is correct. Response: {error_message}"
            )
        elif resp.status_code == 403:
            current_app.logger.error(
                f"Email API access forbidden (403) for {safe_url}. "
                f"Check API key permissions. Response: {error_message}"
            )
        elif resp.status_code == 400:
            current_app.logger.error(
                f"Email API bad request (400) for {safe_url}. "
                f"Check payload format. Response: {error_message}"
            )
        else:
            current_app.logger.error(
                f"Email API error {resp.status_code} for {safe_url}. Response: {error_message}"
            )

        return False
    except Exception as e:
        current_app.logger.error(
            f"Email API request failed for endpoint {api_url_base}: {str(e)}"
        )
        return False
