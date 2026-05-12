import base64
import json
import os
import time
import requests
from requests import Response
from typing import Iterable, Optional, List, Tuple
from flask import current_app
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Response headers logged to help IT compare edge/WAF/proxy vs origin (values truncated).
_EMAIL_API_LOG_RESPONSE_HEADER_EXACT = frozenset(
    {
        "server",
        "via",
        "date",
        "content-type",
        "content-length",
        "transfer-encoding",
        "x-azure-ref",
        "x-ms-request-id",
        "x-ms-edge-ref",
        "request-context",
        "x-correlation-id",
        "x-request-id",
        "request-id",
        "x-cache",
        "x-cdn-pop",
        "cf-ray",
        "x-envoy-upstream-service-time",
        "x-powered-by",
        "x-akamai-request-id",
        "x-amzn-requestid",
        "x-amz-cf-id",
    }
)


def _email_api_edge_headers_for_log(resp: Response) -> str:
    """Safe subset of response headers for WAF / CDN / Azure Front Door / proxy triage."""
    collected: dict = {}
    for name, value in resp.headers.items():
        ln = name.lower()
        if ln in _EMAIL_API_LOG_RESPONSE_HEADER_EXACT or ln.startswith("x-azure") or ln.startswith(
            "x-ms-"
        ):
            v = str(value).replace("\n", " ").replace("\r", " ")
            if len(v) > 200:
                v = v[:200] + "…"
            collected[name] = v
    if not collected:
        return "edge_headers=none_matched_whitelist"
    return " | ".join(f"{k}={collected[k]!r}" for k in sorted(collected.keys()))


def _email_api_response_body_metrics(resp: Response) -> Tuple[int, str, int]:
    """Raw body byte length, primary content-type (no charset), stripped text length."""
    try:
        raw_len = len(resp.content or b"")
    except Exception:
        raw_len = -1
    ct_full = resp.headers.get("Content-Type") or ""
    ct = (ct_full.split(";")[0].strip().lower() or "missing") if ct_full else "missing"
    try:
        text_len = len((resp.text or "").strip())
    except Exception:
        text_len = -1
    return raw_len, ct, text_len


def _email_api_waf_vnet_triage_hint(
    status_code: int,
    body_bytes_len: int,
    text_stripped_len: int,
    response_ct: str,
) -> str:
    """Plain-language hints for logs; compare prod vs staging with same lines."""
    if 200 <= status_code < 300:
        return "compare_envs=if_staging_differs_check_egress_IP_and_response_headers_above"
    hints: List[str] = []
    if body_bytes_len == 0 and status_code >= 400:
        hints.append(
            "empty_response_body_often_gateway_WAF_or_proxy_not_the_mail_API_JSON_validator"
        )
    if body_bytes_len > 0 and "html" in response_ct and status_code >= 400:
        hints.append("HTML_response_body_suggests_WAF_block_page_or_reverse_proxy_error_HTML")
    if status_code in (403, 429, 503):
        hints.append("status_may_be_edge_rate_limit_IP_reputation_or_backpressure_check_WAF_logs")
    hints.append(
        "VNet_NSG_NAT=prod_egress_IP_may_differ_from_staging_firewall_must_allow_HTTPS_to_mail_API_host"
    )
    hints.append("same_app_code_if_staging_OK_headers_and_body_shape_here_vs_staging_pinpoints_network_layer")
    return " ; ".join(hints)


def _b64_utf8(plain: str) -> str:
    return str(base64.b64encode(plain.encode("utf-8")), "utf-8")


def _redact_email_api_url_for_logs(url: str) -> str:
    """Return a log-safe URL: ``apiKey`` / ``apikey`` query values are replaced (never log secrets)."""
    if not url or not str(url).strip():
        return url
    try:
        p = urlparse(url)
        qs = parse_qs(p.query, keep_blank_values=True)
        if not qs:
            return url
        pairs: List[Tuple[str, str]] = []
        for key, vals in qs.items():
            if key.lower() == "apikey":
                for _ in vals or [""]:
                    pairs.append((key, "***REDACTED***"))
            else:
                for v in vals or [""]:
                    pairs.append((key, v))
        new_q = urlencode(pairs, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
    except Exception:
        return "<email_api_url_unparseable>"


def _to_list(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def _is_production_flask_config() -> bool:
    return (os.environ.get("FLASK_CONFIG", "") or "").lower() == "production"


def _failure_warrants_security_event(fail: dict) -> bool:
    code = (fail or {}).get("code") or ""
    if code in ("email_api_http_error", "email_api_request_error"):
        return True
    if code in ("no_email_api_key", "no_email_api_url", "no_default_sender"):
        return _is_production_flask_config()
    return False


def _maybe_record_email_delivery_failure(
    subject: str,
    recipients: List[str],
    failure: dict,
    *,
    suppress_security_hook: bool,
) -> None:
    if suppress_security_hook or not _failure_warrants_security_event(failure):
        return
    try:
        from app.services.security.monitoring import SecurityMonitor

        code = failure.get("code", "unknown")
        subj = (subject or "")[:180]
        desc = f"Email delivery failed ({code}). Subject: {subj}"
        ctx = {
            "failure_code": code,
            "recipient_count": len(recipients or []),
        }
        if failure.get("http_status") is not None:
            ctx["http_status"] = failure.get("http_status")
        ex = failure.get("response_excerpt")
        if ex:
            ctx["response_excerpt"] = str(ex)[:500]

        SecurityMonitor.log_security_event(
            event_type="email_delivery_failure",
            severity="high",
            description=desc,
            context_data=ctx,
            notify_admins=True,
        )
    except Exception as e:
        current_app.logger.error(
            "Failed to record email delivery security event: %s", e, exc_info=True
        )


def _filter_recipients_for_environment(recipients: List[str], cc: List[str], bcc: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    Filter email recipients based on ALLOWED_EMAIL_RECIPIENTS_DEV.

    When the allowlist is non-empty, only those addresses receive mail. Intended for
    local development and staging; **never applied in production** (``FLASK_CONFIG=production``)
    so a mis-set env var cannot block real recipients.
    """
    if (os.environ.get("FLASK_CONFIG", "") or "").lower() == "production":
        return recipients, cc, bcc
    allowed = current_app.config.get("ALLOWED_EMAIL_RECIPIENTS_DEV") or []
    if not allowed:
        return recipients, cc, bcc

    allowed_set = {e.strip().lower() for e in allowed if e and str(e).strip()}
    if not allowed_set:
        return recipients, cc, bcc

    def _filter(lst: List[str]) -> List[str]:
        return [e for e in lst if str(e).strip().lower() in allowed_set]

    return _filter(recipients), _filter(cc), _filter(bcc)


def _ifrc_envelope_to_cc_bcc(
    noreply: str, recipients: List[str], cc: List[str], bcc: List[str]
) -> Tuple[str, str, str]:
    """
    Return plain-text ``(to_address, cc_csv, bcc_csv)`` for IFRC ``*AsBase64`` fields.

    IFRC's gateway matches historical behaviour in this app:
    - **Single** logical To, no Cc/Bcc: put that person in **To** (visible recipient).
    - **Multiple** To, no Cc/Bcc: **To** = noreply, **Bcc** = all To (comma-separated).
    - **To + Cc and/or Bcc:** **To** = noreply, **Cc** / **Bcc** combined as before.
    - **No To** but Cc and/or Bcc: **To** = noreply, pass Cc / Bcc.
    """
    if recipients and not cc and not bcc:
        if len(recipients) == 1:
            return recipients[0], "", ""
        return noreply, "", ",".join(recipients)
    if recipients and (cc or bcc):
        combined_bcc: List[str] = list(recipients)
        if bcc:
            combined_bcc.extend(bcc)
        return noreply, (",".join(cc) if cc else ""), ",".join(combined_bcc)
    if not recipients and (cc or bcc):
        return noreply, (",".join(cc) if cc else ""), (",".join(bcc) if bcc else "")
    return noreply, "", ""


def _ifrc_http_error_diag(
    resp: "requests.Response",
    payload: dict,
    body_b64: str,
    raw_html: str,
    is_single_in_to: bool,
    recipients: List[str],
    cc: List[str],
    bcc: List[str],
) -> str:
    """Safe, no-secrets diagnostic line for IFRC Email API HTTP errors (logs + admin UI)."""
    try:
        approx_json = len(json.dumps(payload, ensure_ascii=False))
    except Exception:
        approx_json = -1
    html_bytes = len(raw_html.encode("utf-8"))
    hdr_id = ""
    for hk in ("X-Request-Id", "X-Correlation-Id", "Request-Id"):
        v = resp.headers.get(hk)
        if v:
            hdr_id = f" {hk}={str(v)[:64]}"
            break
    return (
        f"diag: status={resp.status_code} body_b64_chars={len(body_b64)} "
        f"html_utf8_bytes={html_bytes} json_post_approx={approx_json} "
        f"single_to={is_single_in_to} to_n={len(recipients)} cc_n={len(cc)} bcc_n={len(bcc)}"
        f"{hdr_id}"
    )


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
    _failure_info: Optional[List[dict]] = None,
    _suppress_email_failure_security_event: bool = False,
) -> bool:
    """
    Send an email using the IFRC Email API (HTML body, base64 fields).

    ``text`` and ``reply_to`` are accepted for API compatibility with callers, but
    the current IFRC JSON contract only sends the HTML body; extra fields are not
    added until the gateway documents optional keys (avoids 400s from unknown names).

    Args:
        subject: Email subject line
        recipients: List of recipient email addresses (To field)
        html: HTML email content
        sender: Sender email address (optional, uses MAIL_DEFAULT_SENDER if not provided)
        text: Reserved / not sent in current IFRC payload
        reply_to: Reserved / not sent in current IFRC payload
        cc: List of CC email addresses (optional)
        bcc: List of BCC email addresses (optional)
        importance: Email importance level ('high', 'normal', 'low'). If 'high', adds [HIGH PRIORITY] prefix to subject.
        attachments: Optional list of (filename, content_bytes, content_type) to attach.
        _failure_info: If provided, a single failure dict is appended on False returns
        (``code`` one of: no_recipients, no_default_sender, recipient_allowlist, no_email_api_key,
        no_email_api_url, email_api_http_error, email_api_request_error; ``http_status`` and optional
        ``response_excerpt`` for HTTP error cases).
        _suppress_email_failure_security_event: When True, do not create security events / admin alerts
        for this send (used when sending those alerts to avoid recursion).

    Returns:
        True if email was sent successfully, False otherwise
    """
    sender_email = sender or current_app.config.get("MAIL_DEFAULT_SENDER")
    recipients_list = _to_list(recipients)
    cc_list = _to_list(cc)
    bcc_list = _to_list(bcc)

    if not recipients_list and not cc_list and not bcc_list:
        current_app.logger.warning("send_email called with no recipients")
        if _failure_info is not None:
            _failure_info.append({"code": "no_recipients"})
        return False

    # Validate sender email is configured
    if not sender_email:
        current_app.logger.error(
            "MAIL_DEFAULT_SENDER is not configured. "
            "Please set MAIL_DEFAULT_SENDER in your environment variables."
        )
        fail = {"code": "no_default_sender"}
        if _failure_info is not None:
            _failure_info.append(fail)
        _maybe_record_email_delivery_failure(
            subject,
            recipients_list,
            fail,
            suppress_security_hook=_suppress_email_failure_security_event,
        )
        return False

    # Apply recipient filtering (ALLOWED_EMAIL_RECIPIENTS_DEV, disabled in production)
    recipients_list, cc_list, bcc_list = _filter_recipients_for_environment(recipients_list, cc_list, bcc_list)

    # If all recipients were filtered out, skip send and signal to caller
    if not recipients_list and not cc_list and not bcc_list:
        if _filtered_out is not None:
            _filtered_out.append(True)
        if _failure_info is not None:
            _failure_info.append({"code": "recipient_allowlist"})
        return False

    # Add priority prefix to subject when high or urgent
    final_subject = subject
    if importance == 'urgent':
        if not subject.startswith('[URGENT]'):
            final_subject = f"[URGENT] {subject}"
    elif importance == 'high':
        if not subject.startswith('[HIGH PRIORITY]'):
            final_subject = f"[HIGH PRIORITY] {subject}"

    ok = _send_via_ifrc(
        subject=final_subject,
        sender=sender_email,
        recipients=recipients_list,
        html=html,
        text=text,
        reply_to=reply_to,
        cc=cc_list,
        bcc=bcc_list,
        attachments=attachments,
        _failure_info=_failure_info,
    )
    if not ok and _failure_info and _failure_info[-1]:
        _maybe_record_email_delivery_failure(
            final_subject,
            recipients_list,
            _failure_info[-1],
            suppress_security_hook=_suppress_email_failure_security_event,
        )
    return ok


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
    _failure_info: Optional[List[dict]] = None,
) -> bool:
    """
    Send email via IFRC Email API (base64-encoded fields).

    Envelope shape follows :func:`_ifrc_envelope_to_cc_bcc` (single recipient in To,
    or noreply To + Bcc for bulk, including mixed Cc/Bcc).
    """
    api_key = current_app.config.get("EMAIL_API_KEY")
    api_url_base = (current_app.config.get("EMAIL_API_URL") or "").strip()

    if not api_key:
        current_app.logger.error(
            "Missing EMAIL_API_KEY for Email API. "
            "Please configure EMAIL_API_KEY or environment-specific key (EMAIL_API_KEY_PROD/STG) in your environment."
        )
        if _failure_info is not None:
            _failure_info.append({"code": "no_email_api_key"})
        return False
    if not api_url_base:
        current_app.logger.error(
            "Missing EMAIL_API_URL configuration. "
            "Please set EMAIL_API_URL_PROD or EMAIL_API_URL_STG based on your environment."
        )
        if _failure_info is not None:
            _failure_info.append({"code": "no_email_api_url"})
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

    # Dummy / organizational "To" in the API envelope; real delivery in Cc/Bcc
    fixed_to_address = (current_app.config.get("MAIL_NOREPLY_SENDER") or sender or "").strip() or sender

    # Drop NULs (some DB/editor paths inject them; gateways may reject the JSON or body).
    raw_html = (html or "").strip().replace("\x00", "")
    if not raw_html:
        current_app.logger.warning("send via IFRC: empty HTML body after strip, aborting")
        if _failure_info is not None:
            _failure_info.append({"code": "empty_email_body"})
        return False

    to_addr, out_cc, out_bcc = _ifrc_envelope_to_cc_bcc(fixed_to_address, recipients, cc, bcc)
    is_single_in_to = bool(recipients and not cc and not bcc and len(recipients) == 1)
    has_cc_bcc = bool((out_cc or "").strip() or (out_bcc or "").strip())
    if not is_single_in_to and not has_cc_bcc:
        current_app.logger.error(
            "IFRC email: no delivery addresses after envelope mapping. "
            "This should be unreachable if send_email validated recipients."
        )
        if _failure_info is not None:
            _failure_info.append({"code": "no_recipients"})
        return False

    body_b64 = _b64_utf8(raw_html)
    # IFRC gateway examples (and scripts/test_email.py) always send Cc/Bcc keys; some
    # environments reject payloads when these properties are omitted entirely.
    cc_b64 = _b64_utf8(out_cc) if (out_cc and out_cc.strip()) else ""
    bcc_b64 = _b64_utf8(out_bcc) if (out_bcc and out_bcc.strip()) else ""
    payload: dict = {
        "FromAsBase64": _b64_utf8(sender),
        "ToAsBase64": _b64_utf8(to_addr),
        "CcAsBase64": cc_b64,
        "BccAsBase64": bcc_b64,
        "SubjectAsBase64": _b64_utf8(subject),
        "BodyAsBase64": body_b64,
        "IsBodyHtml": True,
        "TemplateName": "",
        "TemplateLanguage": "",
    }

    # Add attachments if supported by the API (optional; API may use AttachmentsAsBase64 or similar)
    if attachments:
        try:
            payload["Attachments"] = [
                {
                    "FileNameAsBase64": _b64_utf8(fn or "attachment"),
                    "ContentAsBase64": str(base64.b64encode(content), "utf-8"),
                    "ContentType": (ct or "application/octet-stream"),
                }
                for fn, content, ct in attachments
            ]
        except Exception as e:
            current_app.logger.warning("Email attachments skipped (API may not support them): %s", e)

    effective_url = ""
    redacted_url = ""
    try:
        headers = {"Content-Type": "application/json"}

        if api_key_in_url:
            effective_url = api_url
            api_key_appended_by_client = False
        else:
            parsed_url_with_key = urlparse(api_url)
            query_params_with_key = parse_qs(parsed_url_with_key.query)
            query_params_with_key["apiKey"] = [api_key]
            new_query_with_key = urlencode(query_params_with_key, doseq=True)
            effective_url = urlunparse((
                parsed_url_with_key.scheme,
                parsed_url_with_key.netloc,
                parsed_url_with_key.path,
                parsed_url_with_key.params,
                new_query_with_key,
                parsed_url_with_key.fragment
            ))
            api_key_appended_by_client = True

        redacted_url = _redact_email_api_url_for_logs(effective_url)
        parsed_eff = urlparse(effective_url)
        query_names = sorted(parse_qs(parsed_eff.query).keys())
        try:
            approx_json_bytes = len(json.dumps(payload, ensure_ascii=False))
        except Exception:
            approx_json_bytes = -1

        current_app.logger.info(
            "email_api outbound | method=POST | redacted_url=%s | scheme=%s netloc=%s path=%s "
            "query_param_names=%s | api_key_already_in_EMAIL_API_URL=%s api_key_appended_by_app=%s | "
            "request_headers=Content-Type:application/json | json_body_utf8_approx_bytes=%s "
            "payload_keys=%s | BodyAsBase64_chars=%s html_utf8_bytes=%s envelope_single_logical_to=%s | "
            "path_note=HTTPS_TLS_from_this_process_via_requests_library_no_app_HTTP_proxy "
            "egress_IP_is_Azure_subnet_NSG_NAT_or_peer_route_VNet_rules_apply_outside_app",
            redacted_url,
            parsed_eff.scheme or "",
            parsed_eff.netloc or "",
            parsed_eff.path or "/",
            query_names,
            api_key_in_url,
            api_key_appended_by_client,
            approx_json_bytes,
            sorted(payload.keys()),
            len(body_b64),
            len(raw_html.encode("utf-8")),
            is_single_in_to,
        )

        _t_req_start = time.perf_counter()
        resp = requests.post(effective_url, headers=headers, json=payload, timeout=15)
        elapsed_ms = (time.perf_counter() - _t_req_start) * 1000.0

        final_redacted = _redact_email_api_url_for_logs(getattr(resp, "url", "") or "")
        redirect_hops = len(getattr(resp, "history", None) or [])
        raw_len, resp_ct, text_stripped_len = _email_api_response_body_metrics(resp)
        edge_hdr = _email_api_edge_headers_for_log(resp)
        triage_hint = _email_api_waf_vnet_triage_hint(
            resp.status_code, raw_len, text_stripped_len, resp_ct
        )

        corr = ""
        for hk in ("X-Request-Id", "X-Correlation-Id", "Request-Id"):
            v = resp.headers.get(hk)
            if v:
                corr = f"{hk}={str(v)[:96]}"
                break

        url_changed = (final_redacted != redacted_url) and bool(final_redacted)
        current_app.logger.info(
            "email_api response | http_status=%s | elapsed_ms=%.0f | redacted_request_url=%s | "
            "redacted_final_url=%s | redirect_hops=%s | url_changed_after_redirects=%s | "
            "response_bytes=%s | response_content_type=%s | response_text_stripped_len=%s | %s | "
            "edge_headers: %s | waf_vnet_triage: %s",
            resp.status_code,
            elapsed_ms,
            redacted_url,
            final_redacted,
            redirect_hops,
            url_changed,
            raw_len,
            resp_ct,
            text_stripped_len,
            corr or "response_correlation_header=none",
            edge_hdr,
            triage_hint,
        )

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

        t = resp.text
        error_excerpt_full = ""
        if t is not None and str(t).strip():
            error_excerpt_full = str(t)[:2000]
            error_message = error_excerpt_full[:200]
        else:
            # Some gateways return 400 with empty text; try raw bytes for triage
            try:
                raw = (resp.content or b"")[:500]
                if raw:
                    error_excerpt_full = f"(body empty as text, raw len={len(raw)} repr={raw!r})"[:2000]
                    error_message = error_excerpt_full[:200]
                else:
                    error_message = "No response body"
                    error_excerpt_full = error_message
            except Exception:
                error_message = "No response body"
                error_excerpt_full = error_message
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
                "Email API bad request (400) for %s. Response: %s. %s. payload_keys=%s",
                safe_url,
                error_message,
                _ifrc_http_error_diag(
                    resp, payload, body_b64, raw_html, is_single_in_to, recipients, cc, bcc
                ),
                sorted(payload.keys()),
            )
        else:
            current_app.logger.error(
                "Email API error %s for %s. Response: %s. %s",
                resp.status_code,
                safe_url,
                error_message,
                _ifrc_http_error_diag(
                    resp, payload, body_b64, raw_html, is_single_in_to, recipients, cc, bcc
                ),
            )

        if _failure_info is not None:
            fail: dict = {"code": "email_api_http_error", "http_status": resp.status_code}
            diag = _ifrc_http_error_diag(
                resp, payload, body_b64, raw_html, is_single_in_to, recipients, cc, bcc
            )
            excerpt = (error_excerpt_full or "").strip()
            if not excerpt or excerpt == "No response body":
                excerpt = f"No response body. {diag}"
            else:
                excerpt = f"{excerpt} | {diag}"
            fail["response_excerpt"] = excerpt
            fail["html_utf8_bytes"] = len(raw_html.encode("utf-8"))
            fail["body_b64_chars"] = len(body_b64)
            _failure_info.append(fail)
        return False
    except Exception as e:
        err_url = redacted_url or _redact_email_api_url_for_logs(api_url_base)
        current_app.logger.error(
            "Email API request failed (no HTTP response) | redacted_url=%s | error=%s",
            err_url,
            str(e),
            exc_info=True,
        )
        if _failure_info is not None:
            _failure_info.append({"code": "email_api_request_error"})
        return False
