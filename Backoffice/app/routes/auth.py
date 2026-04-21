from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# ========== File: app/routes/auth.py ==========
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort, make_response
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
# Removed check_password_hash as it's now in the User model method
from app.models import User
from app import db # db instance might not be needed here unless modifying user on login
from sqlalchemy.exc import IntegrityError
from app.forms.auth_forms import LoginForm, AccountSettingsForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm
from urllib.parse import urlencode
import os
import requests
import base64
import hashlib
import secrets
import json
import jwt
from jwt.algorithms import RSAAlgorithm
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.services.user_analytics_service import (
    log_login_attempt, log_logout, start_user_session, log_user_activity, log_user_activity_for_user,
    create_security_event, get_client_ip
)
from app.utils.redirect_utils import safe_redirect, is_safe_redirect_url
from app.utils.rate_limiting import auth_rate_limit, password_reset_rate_limit
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.password_validator import validate_password_strength
from app.models import PasswordResetToken
import uuid
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
from app.extensions import mail, csrf
from app.services.email.client import send_email
from app.services.app_settings_service import get_organization_name, is_organization_email, user_has_ai_beta_access
from app.utils.constants import PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS
from app.utils.request_utils import clear_mobile_app_embed_cookie

bp = Blueprint("auth", __name__)

_ACCOUNT_LOCKOUT_THRESHOLD = 10  # consecutive failures before temporary lockout
_ACCOUNT_LOCKOUT_WINDOW_MINUTES = 15  # window in which failures are counted
_ACCOUNT_LOCKOUT_DURATION_MINUTES = 15  # how long lockout lasts


def _is_account_locked_out(email: str) -> bool:
    """Check if an account is temporarily locked due to repeated login failures."""
    try:
        from app.models.core import UserLoginLog
        cutoff = utcnow() - timedelta(minutes=_ACCOUNT_LOCKOUT_WINDOW_MINUTES)
        recent_failures = UserLoginLog.query.filter(
            UserLoginLog.email_attempted == email,
            UserLoginLog.event_type == 'login_failed',
            UserLoginLog.timestamp >= cutoff,
        ).order_by(UserLoginLog.timestamp.desc()).limit(_ACCOUNT_LOCKOUT_THRESHOLD + 1).all()

        if len(recent_failures) < _ACCOUNT_LOCKOUT_THRESHOLD:
            return False

        last_success = UserLoginLog.query.filter(
            UserLoginLog.email_attempted == email,
            UserLoginLog.event_type == 'login',
            UserLoginLog.timestamp >= cutoff,
        ).order_by(UserLoginLog.timestamp.desc()).first()

        if last_success and recent_failures:
            failures_after_success = [f for f in recent_failures if f.timestamp > last_success.timestamp]
            return len(failures_after_success) >= _ACCOUNT_LOCKOUT_THRESHOLD

        return True
    except Exception as e:
        current_app.logger.error(
            "SECURITY: Account lockout check failed — denying login as a precaution: %s", e
        )
        return True


def _flag_deactivated_account_login_attempt(*, user: User, auth_method: str, email: str, password_verified: bool | None = None) -> None:
    """
    Create a high-visibility security event for admins when a deactivated user attempts to log in.
    """
    try:
        create_security_event(
            event_type='deactivated_account_login_attempt',
            severity='high',
            description=f"Deactivated account attempted login ({auth_method}) for {email}",
            context_data={
                'target_user_id': user.id,
                'email': email,
                'auth_method': auth_method,
                'password_verified': password_verified,
                'user_active': bool(getattr(user, 'active', True)),
                'deactivated_at': getattr(user, 'deactivated_at', None).isoformat() if getattr(user, 'deactivated_at', None) else None,
            },
            user_id=user.id,
        )
    except Exception as e:
        current_app.logger.debug("create_security_event failed (non-blocking): %s", e)
        with suppress(Exception):
            current_app.logger.exception("Failed to create security event for deactivated login attempt")

def _get_test_passwords():
    """Get test passwords for quick login buttons (development only)."""
    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    test_passwords = {}
    if flask_config in ['development', 'default']:
        # SECURITY: do not provide hardcoded password fallbacks.
        # Quick-login buttons are only enabled when explicit env vars are set.
        admin_pw = (os.environ.get('TEST_ADMIN_PASSWORD') or '').strip()
        focal_pw = (os.environ.get('TEST_FOCAL_PASSWORD') or '').strip()
        sys_pw = (os.environ.get('TEST_SYS_MANAGER_PASSWORD') or '').strip()
        if admin_pw and focal_pw:
            test_passwords['admin'] = admin_pw
            test_passwords['focal'] = focal_pw
        if sys_pw:
            test_passwords['sys_manager'] = sys_pw
    return test_passwords

@bp.route("/login", methods=["GET", "POST"])
@auth_rate_limit()
def login():
    if current_user.is_authenticated:
        # If already authenticated, respect the 'next' parameter if provided
        next_page = request.args.get('next')
        if next_page and is_safe_redirect_url(next_page):
            return redirect(next_page)
        return redirect(url_for("main.dashboard")) # Redirect if already logged in

    form = LoginForm()
    register_form = RegisterForm()
    forgot_form = ForgotPasswordForm()
    if form.validate_on_submit():
        submitted_email = (form.email.data or '').strip().lower()
        submitted_password = form.password.data or ''
        from app.services import UserService
        user = UserService.get_by_email(submitted_email)

        flask_config = os.environ.get('FLASK_CONFIG', '').lower()
        is_development = flask_config in ('development', 'default')

        # SECURITY: Block all test-prefixed and sys-manager accounts outside development.
        _local_part = submitted_email.split('@')[0] if '@' in submitted_email else ''
        _is_test_email = (
            _local_part.startswith('test_')
            or _local_part == 'sys-manager'
        )
        if _is_test_email and not is_development:
            current_app.logger.warning(
                "SECURITY: Blocked test-user login attempt (%s) in %s environment.",
                submitted_email, flask_config,
            )
            log_login_attempt(submitted_email, success=False, failure_reason='test_user_blocked')
            flash(_("Invalid email or password."), "warning")
            return render_template("auth/login.html", form=form, register_form=register_form, forgot_form=forgot_form, open_modal='', flask_config=flask_config, test_passwords=_get_test_passwords())
        # Re-fetch user after potential creation/update
        from app.services import UserService
        try:
            user = UserService.get_by_email(submitted_email)
        except Exception as e:
            current_app.logger.error(f"Error fetching user after login attempt: {e}", exc_info=True)
            user = None

        if _is_account_locked_out(submitted_email):
            log_login_attempt(submitted_email, success=False, failure_reason='account_locked')
            flash(_("Too many failed login attempts. Please try again later."), "warning")
            return render_template(
                "auth/login.html",
                form=form,
                register_form=register_form,
                forgot_form=forgot_form,
                open_modal='',
                flask_config=flask_config,
                test_passwords=_get_test_passwords(),
            )

        failure_reason = None

        password_ok = bool(user and user.check_password(submitted_password))

        if not user:
            failure_reason = 'user_not_found'
        elif not password_ok:
            failure_reason = 'wrong_password'

        # If the account is deactivated, refuse login and show a clear message (only when identity is confirmed).
        if user and not user.is_active:
            if password_ok:
                # Confirmed identity -> inform the user and flag for admin review
                log_login_attempt(submitted_email, success=False, failure_reason='account_disabled')
                _flag_deactivated_account_login_attempt(
                    user=user,
                    auth_method='password',
                    email=submitted_email,
                    password_verified=True,
                )
                flash(_("Your account is deactivated. Please contact an administrator to reactivate it."), "warning")
            else:
                # Avoid user enumeration: keep messaging generic if password is not verified
                log_login_attempt(submitted_email, success=False, failure_reason=failure_reason)
                flash(_("Invalid email or password."), "warning")
            return render_template(
                "auth/login.html",
                form=form,
                register_form=register_form,
                forgot_form=forgot_form,
                open_modal='',
                flask_config=flask_config,
                test_passwords=_get_test_passwords(),
            )

        if user and password_ok:
            # Prevent session fixation: clear pre-auth session data before binding user
            session.clear()

            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            session['session_start'] = utcnow().isoformat()
            session['last_activity'] = utcnow().isoformat()
            session.permanent = True

            login_user(user)

            # Log successful login
            log_login_attempt(user.email, success=True, user=user, session_id=session_id)

            # Start session tracking
            start_user_session(user, session_id)

            # Log the login activity
            log_user_activity(
                activity_type='login',
                description=f'User {user.email} logged in successfully',
                context_data={
                    'user_id': user.id,
                    'session_id': session_id
                }
            )

            # Securely redirect to the intended page or dashboard (next can come from URL or form)
            next_page = request.args.get('next') or request.form.get('next')
            if current_app.debug and next_page:
                current_app.logger.debug(f"Login redirect: next_page={next_page}")

            # Use safe redirect utility to prevent open redirect vulnerabilities
            return safe_redirect(next_page, default_route='main.dashboard')

        else:
            # Log failed login attempt with specific reason
            log_login_attempt(form.email.data, success=False, failure_reason=failure_reason)
            flash(_("Invalid email or password."), "warning")

    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    return render_template("auth/login.html", form=form, register_form=register_form, forgot_form=forgot_form, title="Login", flask_config=flask_config, test_passwords=_get_test_passwords())

# ===== Azure AD B2C (OIDC) Integration =====
def _b2c_get_required_config() -> dict | None:
    """Fetch required Azure B2C config from Flask config/env.
    Returns None if anything important is missing.
    """
    tenant = current_app.config.get("AZURE_B2C_TENANT")  # e.g. ifrcorgb2cprod.onmicrosoft.com
    policy = current_app.config.get("AZURE_B2C_POLICY")  # e.g. B2C_1A_PROD_MASTER_SIGNUP_SIGNIN
    client_id = current_app.config.get("AZURE_B2C_CLIENT_ID")
    client_secret = current_app.config.get("AZURE_B2C_CLIENT_SECRET")
    redirect_uri = current_app.config.get("AZURE_B2C_REDIRECT_URI") or url_for("auth.azure_callback", _external=True)
    scope = current_app.config.get("AZURE_B2C_SCOPE", "openid email profile")
    if not (tenant and policy and client_id and client_secret and redirect_uri):
        return None
    return {
        "tenant": tenant,
        "policy": policy,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }

def _b2c_metadata(tenant: str, policy: str) -> dict:
    subdomain = tenant.split(".")[0]
    metadata_url = f"https://{subdomain}.b2clogin.com/{tenant}/{policy}/v2.0/.well-known/openid-configuration"
    r = requests.get(metadata_url, timeout=10)
    r.raise_for_status()
    return r.json()

def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64).replace("_", "-").replace(".", "-")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge

def _decode_jwt_payload_unverified(id_token: str) -> dict | None:
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # add padding
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(decoded)
    except Exception as e:
        current_app.logger.debug("JWT payload decode failed: %s", e)
        return None

def _verify_and_decode_id_token(id_token: str, meta: dict, audience: str, expected_nonce: str | None) -> dict | None:
    try:
        jwks_uri = meta.get('jwks_uri')
        if not jwks_uri:
            return None
        # Fetch JWKS
        jwks_resp = requests.get(jwks_uri, timeout=10)
        jwks_resp.raise_for_status()
        jwks = jwks_resp.json().get('keys', [])
        headers = jwt.get_unverified_header(id_token)
        kid = headers.get('kid')
        public_key = None
        for jwk in jwks:
            if jwk.get('kid') == kid:
                public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
                break
        if public_key is None:
            return None
        decoded = jwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=meta.get('issuer')
        )
        # Nonce check
        if expected_nonce and decoded.get('nonce') != expected_nonce:
            return None
        return decoded
    except Exception as e:
        current_app.logger.debug("JWT verify failed: %s", e)
        return None

def _mobile_deep_link_for_user(user, existing_session_id=None):
    """Issue a JWT token pair and return a ``humdatabank://oauth-success`` redirect.

    Used when a mobile Chrome Custom Tab OAuth flow hits an endpoint where the
    user is *already* authenticated via the web session cookie, so the normal
    Azure callback code path is skipped entirely.  We still need to deliver JWT
    tokens to the Flutter app via the deep link.
    """
    from app.utils.mobile_jwt import issue_token_pair
    from urllib.parse import urlencode as _urlencode
    session_id = existing_session_id or session.get('session_id') or secrets.token_urlsafe(16)
    tokens = issue_token_pair(user.id, session_id=session_id)
    deep_link = (
        "humdatabank://oauth-success?"
        + _urlencode({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_in": tokens["expires_in"],
        })
    )
    current_app.logger.info(
        "Mobile OAuth (already-authenticated): issuing JWT tokens via deep link for user %s", user.id
    )
    return redirect(deep_link)


@bp.route("/login/azure")
def azure_login():
    if current_user.is_authenticated:
        if request.args.get("mobile_return_scheme") == "humdatabank":
            # Mobile Chrome Custom Tab OAuth flow.
            #
            # Do NOT short-circuit to _mobile_deep_link_for_user here.
            # Chrome Custom Tabs share the system-browser cookie store.  When
            # the user logs out of the mobile app the JWT tokens are cleared
            # locally, but the Flask session cookie that was written during the
            # previous Azure OAuth flow is STILL alive in Chrome's store.  If
            # we honour that stale session and issue fresh JWTs immediately the
            # user never has to re-authenticate with Azure after logging out.
            #
            # Fix: clear the web session now so the browser receives a cleared
            # Set-Cookie in this response.  Subsequent requests in the same CCT
            # tab (Azure redirect → callback) will carry the new empty cookie,
            # causing `current_user.is_authenticated` to be False at callback
            # time, and the full Azure auth code exchange will proceed normally.
            current_app.logger.info(
                "Mobile OAuth: clearing stale web session for user %s before Azure redirect",
                current_user.id,
            )
            logout_user()
            session.clear()
            session.modified = True
            # Fall through to the Azure authorisation redirect below.
        else:
            return redirect(url_for("main.dashboard"))

    cfg = _b2c_get_required_config()
    if not cfg:
        flash("Azure login is not configured. Please set AZURE_B2C_* settings.", "warning")
        return redirect(url_for("auth.login"))

    try:
        meta = _b2c_metadata(cfg["tenant"], cfg["policy"])
    except Exception as e:
        current_app.logger.warning("Azure B2C metadata fetch failed: %s", e)
        flash("Azure login is temporarily unavailable.", "danger")
        return redirect(url_for("auth.login"))

    verifier, challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)

    next_url = request.args.get("next")
    if not (next_url and is_safe_redirect_url(next_url)):
        next_url = None

    # Mobile app (Chrome Custom Tabs) passes this to request JWT token delivery
    # via a deep link instead of relying on the session cookie.
    is_mobile_oauth = request.args.get("mobile_return_scheme") == "humdatabank"

    import time as _time

    # Primary: embed the OAuth state data in a signed JWT passed as the "state"
    # parameter to Azure.  The callback decodes it directly without needing the
    # Flask session cookie — this fixes Android WebView SameSite=Lax issues
    # where the cookie is dropped across the microsoftonline.com redirect chain.
    _now = int(_time.time())
    signed_state = jwt.encode(
        {
            "_state": state,    # inner CSRF token
            "verifier": verifier,
            "nonce": nonce,
            "next": next_url,
            "mobile": is_mobile_oauth,  # mobile app: deliver tokens via deep link
            "iat": _now,
            "exp": _now + 600,  # 10-minute window
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    # Also keep a session fallback for browser logins and rolling-deployment
    # backward compat (browsers that correctly forward SameSite=Lax cookies).
    session.permanent = True
    pending = session.get("b2c_pending") or {}
    pending[state] = {"verifier": verifier, "nonce": nonce, "next": next_url, "mobile": is_mobile_oauth}
    if len(pending) > 5:
        oldest_states = list(pending.keys())[:-5]
        for old in oldest_states:
            pending.pop(old, None)
    session["b2c_pending"] = pending
    session.modified = True

    auth_url = meta.get("authorization_endpoint")
    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "redirect_uri": cfg["redirect_uri"],
        "response_mode": "query",
        "scope": cfg["scope"],
        "state": signed_state,  # signed JWT carries verifier/nonce/next
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    # Force re-authentication for mobile flows so that logging out of the app
    # actually requires the user to sign in with Azure again.  Chrome Custom
    # Tabs share the system browser's cookie store, so without this the B2C SSO
    # session silently re-authenticates the user after a mobile logout.
    if is_mobile_oauth:
        params["prompt"] = "login"
    return redirect(f"{auth_url}?{urlencode(params)}")

@bp.route("/auth/azure/callback", methods=["GET", "POST"])
@csrf.exempt
def azure_callback():
    if current_user.is_authenticated:
        # Peek at the signed-JWT state to check whether this is a mobile flow.
        # Chrome Custom Tabs carries the web session cookie, so an already-logged-in
        # user hits this early-exit and never receives the deep-link JWT tokens.
        _state_param = request.values.get("state")
        if _state_param:
            try:
                _decoded_peek = jwt.decode(
                    _state_param,
                    current_app.config["SECRET_KEY"],
                    algorithms=["HS256"],
                )
                if _decoded_peek.get("mobile"):
                    try:
                        return _mobile_deep_link_for_user(current_user)
                    except Exception as e:
                        current_app.logger.error(
                            "Mobile OAuth (already-authed callback): JWT issuance failed: %s", e, exc_info=True
                        )
            except Exception:
                pass
        return redirect(url_for("main.dashboard"))

    cfg = _b2c_get_required_config()
    if not cfg:
        flash("Azure login is not configured. Please set AZURE_B2C_* settings.", "warning")
        return redirect(url_for("auth.login"))

    # Handle error from B2C (may arrive via GET query or POST form_post)
    error = request.values.get("error")
    error_description = request.values.get("error_description")
    if error:
        # User canceled from B2C UI
        if error_description and "AADB2C90091" in error_description:
            return redirect(url_for("auth.login"))
        flash(_("Azure sign-in failed."), "warning")
        return redirect(url_for("auth.login"))

    code = request.values.get("code")
    state = request.values.get("state")
    if not code or not state:
        flash(_("Invalid Azure callback."), "warning")
        return redirect(url_for("auth.login"))

    session.permanent = True

    # Primary path: decode the signed-JWT state.  This works even when the Flask
    # session cookie was not forwarded by the client (Android WebView SameSite=Lax).
    verifier = nonce = next_page_from_state = None
    _jwt_state_ok = False
    _mobile_oauth = False  # True when mobile app requested token delivery via deep link
    try:
        _decoded = jwt.decode(
            state,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
        verifier = _decoded.get("verifier")
        nonce = _decoded.get("nonce")
        next_page_from_state = _decoded.get("next")
        _mobile_oauth = bool(_decoded.get("mobile", False))
        # Clean up any matching session entry that a browser may have stored.
        _inner = _decoded.get("_state", "")
        _sess_pending = session.get("b2c_pending") or {}
        _sess_pending.pop(_inner, None)
        session["b2c_pending"] = _sess_pending
        session.modified = True
        _jwt_state_ok = True
    except jwt.ExpiredSignatureError:
        current_app.logger.warning("Azure OAuth state JWT expired (state prefix=%s)", state[:20])
        flash(_("Login session expired. Please try signing in again."), "warning")
        return redirect(url_for("auth.login"))
    except (jwt.InvalidTokenError, Exception):
        pass  # Not a signed JWT — fall through to session-based lookup

    if not _jwt_state_ok:
        # Fallback: session-cookie-based lookup for browsers and in-flight
        # requests that started before the signed-JWT approach was deployed.
        pending = session.get("b2c_pending") or {}
        auth_data = pending.pop(state, None)
        if auth_data is None:
            stored_state = session.get("b2c_state")
            if state != stored_state:
                current_app.logger.warning(
                    "State mismatch in Azure callback: received=%s, stored=%s, "
                    "pending_keys=%s, session_keys=%s",
                    state, stored_state, list(pending.keys()), list(session.keys()),
                )
                flash(_("State mismatch. Please try signing in again."), "warning")
                return redirect(url_for("auth.login"))
            verifier = session.pop("b2c_code_verifier", None)
            nonce = session.pop("b2c_nonce", None)
            next_page_from_state = session.pop("b2c_next", None)
        else:
            session["b2c_pending"] = pending
            session.modified = True
            verifier = auth_data.get("verifier")
            nonce = auth_data.get("nonce")
            next_page_from_state = auth_data.get("next")
            _mobile_oauth = bool(auth_data.get("mobile", False))

    _nonce_for_verify = nonce
    try:
        meta = _b2c_metadata(cfg["tenant"], cfg["policy"])  # token endpoint, userinfo, etc.
    except Exception as e:
        current_app.logger.warning("Azure B2C metadata fetch failed (callback): %s", e)
        flash("Azure login is temporarily unavailable.", "danger")
        return redirect(url_for("auth.login"))

    token_data = {
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_secret": cfg["client_secret"],
        "code_verifier": verifier,
    }
    try:
        tr = requests.post(meta.get("token_endpoint"), data=token_data, timeout=10)
        tr.raise_for_status()
        tokens = tr.json()
    except Exception as e:
        current_app.logger.warning("Azure token exchange failed: %s", e)
        flash(_("Could not complete Azure sign-in."), "danger")
        return redirect(url_for("auth.login"))

    id_token = tokens.get("id_token")
    access_token = tokens.get("access_token")
    claims = None
    if id_token:
        claims = _verify_and_decode_id_token(id_token, meta, cfg["client_id"], _nonce_for_verify)
        if not claims:
            current_app.logger.error(
                "SECURITY: Azure B2C ID token verification failed — rejecting login. "
                "Check JWKS endpoint, client_id, and nonce configuration."
            )
            flash("Login failed: identity token could not be verified. Please try again.", "danger")
            return redirect(url_for("auth.login"))

    # Log all claims received for debugging
    if claims:
        current_app.logger.info(f"Azure B2C ID Token Claims: {list(claims.keys())}")
        current_app.logger.debug(f"Azure B2C Full Claims: {claims}")
    else:
        current_app.logger.warning("No claims found in ID token")

    email = None
    display_name = None
    given_name = None
    family_name = None
    sub = None
    if claims:
        email = claims.get("email") or claims.get("preferred_username")
        display_name = claims.get("name")
        given_name = claims.get("given_name")
        family_name = claims.get("family_name")
        sub = claims.get("sub")
        current_app.logger.info(f"Extracted from ID token - email: {email}")

    # Try userinfo endpoint to recover missing identity fields.
    if access_token and meta.get("userinfo_endpoint"):
        try:
            current_app.logger.info(f"Fetching userinfo from: {meta.get('userinfo_endpoint')}")
            ur = requests.get(meta.get("userinfo_endpoint"), headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
            if ur.ok:
                ui = ur.json()
                current_app.logger.info(f"Userinfo response keys: {list(ui.keys())}")
                current_app.logger.debug(f"Userinfo full response: {ui}")

                # Get email if not already present
                if not email:
                    email = ui.get("email") or ui.get("preferred_username")
                    display_name = display_name or ui.get("name")
                    given_name = given_name or ui.get("given_name")
                    family_name = family_name or ui.get("family_name")
                    sub = sub or ui.get("sub")
            else:
                current_app.logger.warning(f"Userinfo endpoint returned status {ur.status_code}: {ur.text}")
        except Exception as e:
            current_app.logger.error(f"Error fetching userinfo: {e}", exc_info=True)

    if not email:
        current_app.logger.error("Could not retrieve email from Azure B2C")
        flash(_("We could not retrieve your email from Azure."), "danger")
        return redirect(url_for("auth.login"))

    submitted_email = email.strip().lower()
    current_app.logger.info(f"Processing Azure login for email: {submitted_email}")
    from app.services import UserService
    user = UserService.get_by_email(submitted_email)

    if not user:
        # Create a minimal user (RBAC-only)
        current_app.logger.info(f"Creating new user account for: {submitted_email}")
        user = User(email=submitted_email)
        # Derive a sensible name if available
        if display_name:
            user.name = display_name
        elif given_name or family_name:
            user.name = f"{(given_name or '').strip()} {(family_name or '').strip()}".strip()
        db.session.add(user)
        try:
            db.session.flush()
            current_app.logger.info(f"Successfully created user {user.id}")
            # Assign baseline RBAC role (best-effort)
            try:
                from app.models.rbac import RbacRole, RbacUserRole
                fp_role = RbacRole.query.filter_by(code="assignment_editor_submitter").first()
                if not fp_role:
                    fp_role = RbacRole(code="assignment_editor_submitter", name="Assignment Editor & Submitter", description="Can enter data and submit assignments.")
                    db.session.add(fp_role)
                    db.session.flush()
                exists = RbacUserRole.query.filter_by(user_id=user.id, role_id=fp_role.id).first()
                if not exists:
                    db.session.add(RbacUserRole(user_id=user.id, role_id=fp_role.id))
                    db.session.flush()
            except Exception as e:
                current_app.logger.warning(f"RBAC: could not assign default role for Azure-created user: {e}", exc_info=True)
            try:
                log_user_activity_for_user(
                    user.id,
                    'account_created',
                    'User account auto-created via Azure AD B2C login',
                    {
                        'email': user.email,
                        'source': 'azure_b2c',
                        'display_name': display_name
                    }
                )
            except Exception as e:
                current_app.logger.warning(f"Failed to log user activity: {e}", exc_info=True)

            # Send welcome email
            try:
                from app.services.email.service import send_welcome_email
                send_welcome_email(user)
            except Exception as e:
                current_app.logger.error(f"Failed to send welcome email to {user.email}: {e}", exc_info=True)
                # Don't fail user creation if email fails
        except IntegrityError as e:
            request_transaction_rollback()
            # After a DB dump/restore, sequences can be behind so INSERT gets duplicate key.
            # Reset the user sequence so future signups work, then re-fetch by email and proceed.
            from app.utils.sequence_utils import reset_user_sequence
            if reset_user_sequence():
                current_app.logger.info("Reset user table sequence after duplicate key (e.g. post-dump).")
            dup_user = UserService.get_by_email(submitted_email)
            if dup_user:
                current_app.logger.info(
                    "User already existed (e.g. sequence out of sync after DB restore), proceeding with login."
                )
                user = dup_user
            else:
                current_app.logger.error(f"Failed to create user from Azure login: {e}", exc_info=True)
                flash(_("Could not create user from Azure login."), "danger")
                return redirect(url_for("auth.login"))
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Failed to create user from Azure login: {e}", exc_info=True)
            flash(_("Could not create user from Azure login."), "danger")
            return redirect(url_for("auth.login"))

    # Block deactivated users from logging in via Azure and flag for admin review.
    if user and not user.is_active:
        log_login_attempt(submitted_email, success=False, failure_reason='account_disabled')
        _flag_deactivated_account_login_attempt(
            user=user,
            auth_method='azure_b2c',
            email=submitted_email,
            password_verified=None,
        )
        flash(_("Your account is deactivated. Please contact an administrator to reactivate it."), "warning")
        # Clean PKCE vars (best effort) — both dict-based and legacy single-key
        session.pop('b2c_pending', None)
        session.pop('b2c_code_verifier', None)
        session.pop('b2c_state', None)
        session.pop('b2c_nonce', None)
        return redirect(url_for("auth.login"))

    # Prevent session fixation: clear pre-auth session data before binding user
    session.clear()

    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    session['session_start'] = utcnow().isoformat()
    session['last_activity'] = utcnow().isoformat()
    session.permanent = True
    if id_token:
        session['b2c_id_token'] = id_token

    login_user(user)

    # Log successful login
    with suppress(Exception):
        log_login_attempt(user.email, success=True, user=user, session_id=session_id)
        start_user_session(user, session_id)
        log_user_activity(
            activity_type='login',
            description=f'User {user.email} logged in via Azure AD B2C',
            context_data={'user_id': user.id, 'session_id': session_id, 'idp': 'azure_b2c'}
        )

    # Clean up any legacy single-key PKCE vars left from old deployments
    session.pop('b2c_code_verifier', None)
    session.pop('b2c_state', None)
    session.pop('b2c_nonce', None)
    session.pop('b2c_next', None)

    # Mobile app (Chrome Custom Tabs flow): deliver JWT tokens via deep link
    # instead of a session cookie so the native app can authenticate API calls.
    if _mobile_oauth:
        try:
            from app.utils.mobile_jwt import issue_token_pair
            from urllib.parse import urlencode as _urlencode
            tokens = issue_token_pair(user.id, session_id=session_id)
            deep_link = (
                "humdatabank://oauth-success?"
                + _urlencode({
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens["refresh_token"],
                    "expires_in": tokens["expires_in"],
                })
            )
            current_app.logger.info("Mobile OAuth: redirecting to deep link for user %s", user.id)
            return redirect(deep_link)
        except Exception as e:
            current_app.logger.error("Mobile OAuth: failed to issue JWT tokens: %s", e, exc_info=True)
            # Fall through to normal web redirect as a best-effort fallback

    # Use safe redirect utility to prevent open redirect vulnerabilities
    return safe_redirect(next_page_from_state, default_route='main.dashboard')

@bp.route("/logout")
@login_required # Ensure user is logged in before logging out
def logout():
    # Calculate session duration
    session_duration = None
    if 'session_start' in session:
        with suppress(Exception):
            session_start = datetime.fromisoformat(session['session_start'])
            session_duration = int((utcnow() - session_start).total_seconds() / 60)

    # Log logout activity
    log_user_activity(
        activity_type='logout',
        description=f'User {current_user.email} logged out',
        context_data={
            'user_id': current_user.id,
            'session_duration_minutes': session_duration
        }
    )

    # Log logout event
    log_logout(current_user, session_duration_minutes=session_duration)

    def _logout_redirect(location: str):
        resp = make_response(redirect(location))
        return clear_mobile_app_embed_cookie(resp)

    # Grab the B2C id_token before wiping the session (needed for id_token_hint)
    b2c_id_token = session.get('b2c_id_token')

    logout_user()

    # Fully wipe the local session so no state survives
    session.clear()

    # On localhost/dev, skip B2C logout: B2C often rejects localhost redirect URIs
    # and requires id_token_hint, which can fail in dev. Just redirect to login.
    post_logout_uri = (
        current_app.config.get("AZURE_B2C_POST_LOGOUT_REDIRECT_URI")
        or url_for("auth.login", _external=True)
    )
    if "localhost" in post_logout_uri or "127.0.0.1" in post_logout_uri:
        return _logout_redirect(url_for("auth.login"))

    # End the Azure B2C SSO session so the user must re-authenticate with B2C
    # on next login (prevents silent re-login after logout).
    cfg = _b2c_get_required_config()
    if cfg:
        with suppress(Exception):
            meta = _b2c_metadata(cfg["tenant"], cfg["policy"])
            end_session_endpoint = meta.get("end_session_endpoint")
            if end_session_endpoint:
                params = {'post_logout_redirect_uri': post_logout_uri}
                if b2c_id_token:
                    params['id_token_hint'] = b2c_id_token
                logout_url = f"{end_session_endpoint}?{urlencode(params)}"
                return _logout_redirect(logout_url)

    return _logout_redirect(url_for("auth.login"))

def _generate_reset_token(email: str) -> str | None:
    """
    Generate a password reset token and store it in the database.

    Returns:
        The reset token string, or None if DB storage failed (fail-closed).
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(email, salt='password-reset-salt')

    # Store token in database for tracking
    from app.services import UserService
    user = UserService.get_by_email(email)
    if user:
        try:
            # Revoke all existing unused tokens for this user
            PasswordResetToken.revoke_all_user_tokens(user.id)

            # Create new token record
            token_hash = PasswordResetToken.hash_token(token)
            expires_at = utcnow() + timedelta(hours=1)

            reset_token = PasswordResetToken(
                token_hash=token_hash,
                user_id=user.id,
                user_email=email,
                expires_at=expires_at,
                ip_address=get_client_ip(),
                user_agent=request.headers.get('User-Agent', '')[:500]  # Limit length
            )
            db.session.add(reset_token)
            db.session.flush()
        except Exception as e:
            current_app.logger.error(f"Failed to store password reset token: {e}", exc_info=True)
            request_transaction_rollback()
            return None

    return token

def _verify_reset_token(token: str, max_age_seconds: int | None = None) -> tuple[str | None, PasswordResetToken | None]:
    """
    Verify a password reset token and check database for validity.

    Returns:
        Tuple of (email, token_record) or (None, None) if invalid
    """
    if max_age_seconds is None:
        max_age_seconds = PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS
    # First verify the token signature
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None, None

    # Check database for token record
    token_hash = PasswordResetToken.hash_token(token)
    reset_token = PasswordResetToken.query.filter_by(
        token_hash=token_hash,
        user_email=email
    ).first()

    # If no record found, token is invalid (not tracked = invalid)
    if not reset_token:
        current_app.logger.warning(f"Password reset token not found in database for email: {email}")
        return None, None

    # Check if token is valid (not used, not revoked, not expired)
    if not reset_token.is_valid():
        current_app.logger.warning(
            "Invalid password reset token attempted: used=%s, revoked=%s, expired=%s",
            reset_token.is_used,
            reset_token.is_revoked,
            (utcnow() > ensure_utc(reset_token.expires_at)),
        )
        return None, None

    return email, reset_token

def _send_password_reset_email(recipient_email: str, token: str) -> bool:
    try:
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        org_name = get_organization_name()
        subject = f'{org_name} - Password Reset'
        html = f"""
        <p>Hello,</p>
        <p>You requested a password reset. Click the link below to set a new password. This link is valid for 1 hour.</p>
        <p><a href="{reset_url}">Reset your password</a></p>
        <p>If you did not request this, you can safely ignore this email.</p>
        <p>— {org_name}</p>
        """
        return send_email(
            subject=subject,
            recipients=[recipient_email],
            html=html,
            sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER'])
        )
    except Exception as e:
        current_app.logger.warning("Password reset email send failed: %s", e)
        return False

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = RegisterForm()
    if request.method == 'GET':
        # Prefer modal usage
        return redirect(url_for('auth.login'))
    # POST
    if form.validate_on_submit():
        from app.services import UserService
        existing = UserService.get_by_email(form.email.data.strip().lower())
        if existing:
            flash(_('An account with this email already exists.'), 'warning')
            # Re-render login with modal open and errors
            flask_config = os.environ.get('FLASK_CONFIG', '').lower()
            return render_template('auth/login.html', form=LoginForm(), register_form=form, forgot_form=ForgotPasswordForm(), open_modal='register', title='Login', flask_config=flask_config, test_passwords=_get_test_passwords())
        # Server-side password strength validation
        is_valid, validation_errors = validate_password_strength(
            form.password.data,
            user_email=form.email.data.strip().lower(),
            user_name=form.name.data
        )

        if not is_valid:
            for error in validation_errors:
                flash(error, 'warning')
            flask_config = os.environ.get('FLASK_CONFIG', '').lower()
            return render_template('auth/login.html', form=LoginForm(), register_form=form, forgot_form=ForgotPasswordForm(), open_modal='register', title='Login', flask_config=flask_config, test_passwords=_get_test_passwords())

        user = User(email=form.email.data.strip().lower(), name=form.name.data or None, title=form.title.data or None)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            # Flush to get user.id without committing
            db.session.flush()
            # Assign baseline RBAC role (best-effort)
            try:
                from app.models.rbac import RbacRole, RbacUserRole
                fp_role = RbacRole.query.filter_by(code="assignment_editor_submitter").first()
                if not fp_role:
                    fp_role = RbacRole(code="assignment_editor_submitter", name="Assignment Editor & Submitter", description="Can enter data and submit assignments.")
                    db.session.add(fp_role)
                    db.session.flush()
                exists = RbacUserRole.query.filter_by(user_id=user.id, role_id=fp_role.id).first()
                if not exists:
                    db.session.add(RbacUserRole(user_id=user.id, role_id=fp_role.id))
                    db.session.flush()
            except Exception as e:
                current_app.logger.warning(f"RBAC: could not assign default role for registered user: {e}", exc_info=True)
            # Create a pending country access request for the selected country
            with suppress(Exception):
                from app.models import CountryAccessRequest
                requested_country_id = form.requested_country_id.data
                if requested_country_id:
                    access_request = CountryAccessRequest(
                        user_id=user.id,
                        country_id=int(requested_country_id),
                        request_message=form.request_message.data or None,
                        status='pending'
                    )
                    db.session.add(access_request)
            db.session.flush()
            with suppress(Exception):
                log_user_activity_for_user(
                    user.id,
                    'account_created',
                    'User created account via email/password registration',
                    {
                        'email': user.email,
                        'requested_country_id': form.requested_country_id.data,
                        'source': 'self_service_form'
                    }
                )
            flash(_('Your account has been created. Your country access request is pending admin approval.'), 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            current_app.logger.warning("Account registration failed: %s", e, exc_info=True)
            request_transaction_rollback()
            flash(_('Could not create account. Please try again.'), 'danger')
            flask_config = os.environ.get('FLASK_CONFIG', '').lower()
            return render_template('auth/login.html', form=LoginForm(), register_form=form, forgot_form=ForgotPasswordForm(), open_modal='register', title='Login', flask_config=flask_config, test_passwords=_get_test_passwords())
    # Validation errors
    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    return render_template('auth/login.html', form=LoginForm(), register_form=form, forgot_form=ForgotPasswordForm(), open_modal='register', title='Login', flask_config=flask_config, test_passwords=_get_test_passwords())

@bp.route('/register/check-email', methods=['GET'])
def check_register_email():
    """
    Lightweight endpoint used by the registration modal to check if an email
    address is already registered. Returns JSON:
      { "ok": true, "exists": true|false }
    """
    email = (request.args.get('email') or '').strip().lower()
    if not email:
        return json_bad_request('missing_email', ok=False)
    from app.services import UserService
    exists = UserService.exists(email)
    return json_ok(ok=True, exists=exists)

@bp.route('/forgot-password', methods=['GET', 'POST'])
@password_reset_rate_limit()
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = ForgotPasswordForm()
    if request.method == 'GET':
        # Prefer modal usage
        return redirect(url_for('auth.login'))
    # POST
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        from app.services import UserService
        user = UserService.get_by_email(email)
        # Always show success to avoid revealing account existence
        if user:
            token = _generate_reset_token(email)
            if token is None:
                flash(_('We could not process the reset request at this time. Please try again later.'), 'danger')
                return redirect(url_for('auth.login'))
            sent = _send_password_reset_email(email, token)
            if not sent:
                flash(_('We could not send the reset email at this time. Please contact support.'), 'danger')
        flash(_('If an account exists for that email, a reset link has been sent.'), 'info')
        return redirect(url_for('auth.login'))
    # Validation errors
    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    return render_template('auth/login.html', form=LoginForm(), register_form=RegisterForm(), forgot_form=form, open_modal='forgot', title='Login', flask_config=flask_config, test_passwords=_get_test_passwords())

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@password_reset_rate_limit()
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    email, reset_token = _verify_reset_token(token)
    if not email or not reset_token:
        flash(_('This reset link is invalid or has expired.'), 'warning')
        return redirect(url_for('auth.forgot_password'))
    from app.services import UserService
    user = UserService.get_by_email(email)
    if not user:
        flash(_('Invalid reset link.'), 'warning')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Server-side password strength validation
        is_valid, validation_errors = validate_password_strength(
            form.password.data,
            user_email=user.email,
            user_name=user.name
        )

        if not is_valid:
            for error in validation_errors:
                flash(error, 'warning')
            return render_template('auth/reset_password.html', form=form, title='Reset Password')

        user.set_password(form.password.data)

        # Mark token as used
        try:
            reset_token.mark_as_used()
            db.session.flush()
        except Exception as e:
            current_app.logger.error(f"Failed to mark password reset token as used: {e}", exc_info=True)
            request_transaction_rollback()
            # Try again with explicit commit
            try:
                reset_token.is_used = True
                reset_token.used_at = utcnow()
                db.session.flush()
            except Exception as e:
                current_app.logger.debug("Fallback reset token mark failed: %s", e)
                request_transaction_rollback()

        with suppress(Exception):
            log_user_activity_for_user(
                user.id,
                'password_reset',
                'User reset password via reset link',
                {
                    'email': user.email,
                    'initiated_by': 'self_service_reset',
                    'token_id': reset_token.id
                }
            )
        flash(_('Your password has been reset. You can now log in.'), 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form, title='Reset Password')
@bp.route("/account-settings", methods=["GET", "POST"])
@login_required
def account_settings():
    """Account settings page for users to update their name and title."""
    form = AccountSettingsForm()
    from app.models import CountryAccessRequest
    from app.models.core import UserEntityPermission
    from app.models.system import CountryAccessRequestStatus
    from app.services.entity_service import EntityService
    from app.forms.auth_forms import RequestCountryAccessForm

    if form.validate_on_submit():
        # Update user information
        current_user.name = form.name.data if form.name.data else None
        current_user.title = form.title.data if form.title.data else None
        current_user.chatbot_enabled = form.chatbot_enabled.data
        current_user.profile_color = form.profile_color.data if form.profile_color.data else '#3B82F6'

        try:
            db.session.flush()
            flash(_("Your account settings have been updated successfully."), "success")

            # Log the activity
            log_user_activity(
                activity_type='profile_update',
                description=f'User {current_user.email} updated their profile information',
                context_data={
                    'user_id': current_user.id,
                    'updated_fields': {
                        'name': form.name.data,
                        'title': form.title.data,
                        'chatbot_enabled': form.chatbot_enabled.data,
                        'profile_color': form.profile_color.data
                    }
                }
            )

            return redirect(url_for('auth.account_settings'))
        except Exception as e:
            request_transaction_rollback()
            flash(_("An error occurred while updating your account settings. Please try again."), "danger")

    # Pre-populate form with current user data for GET request
    if request.method == 'GET':
        form.name.data = current_user.name
        form.title.data = current_user.title
        form.chatbot_enabled.data = current_user.chatbot_enabled
        form.profile_color.data = current_user.profile_color if current_user.profile_color else '#3B82F6'

    # Get user's registered devices
    from app.models.system import UserDevice
    registered_devices = UserDevice.query.filter_by(user_id=current_user.id) \
        .order_by(UserDevice.last_active_at.desc().nullslast(), UserDevice.created_at.desc().nullslast()) \
        .all()

    # Entity permissions for display in Entity Access tab
    entity_access_list = []
    try:
        entity_permissions = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
        for perm in entity_permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if not entity:
                continue
            entity_access_list.append({
                'entity_type': perm.entity_type,
                'entity_id': perm.entity_id,
                'entity_name': EntityService.get_entity_name(perm.entity_type, perm.entity_id, include_hierarchy=True),
            })
        entity_access_list.sort(key=lambda x: (x['entity_type'], x['entity_name']))
    except Exception as e:
        current_app.logger.error("Failed to load entity access for account settings: %s", e, exc_info=True)
        entity_access_list = []

    # Country access request form and request history
    request_access_form = RequestCountryAccessForm(user_id=current_user.id)
    all_access_requests = []
    pending_access_requests = []
    try:
        all_access_requests = (
            CountryAccessRequest.query.filter_by(user_id=current_user.id)
            .order_by(CountryAccessRequest.created_at.desc())
            .all()
        )
        for req in all_access_requests:
            if req.status == CountryAccessRequestStatus.APPROVED and req.country_id:
                req._access_revoked = not current_user.has_entity_access('country', req.country_id)
            else:
                req._access_revoked = False
        pending_access_requests = [
            req for req in all_access_requests if req.status == CountryAccessRequestStatus.PENDING
        ]
    except Exception as e:
        current_app.logger.error("Failed to load access requests for account settings: %s", e, exc_info=True)
        all_access_requests = []
        pending_access_requests = []

    return render_template("auth/account_settings.html", form=form, title="Account Settings",
                         chatbot_feature_enabled=(current_app.config.get('CHATBOT_ENABLED', True) and user_has_ai_beta_access(current_user)),
                         registered_devices=registered_devices,
                         entity_access_list=entity_access_list,
                         request_access_form=request_access_form,
                         all_access_requests=all_access_requests,
                         pending_access_requests=pending_access_requests,
                         can_request_multiple_countries=is_organization_email(getattr(current_user, 'email', '')))

@bp.route("/debug/profile-picture", methods=["GET"])
@login_required
def debug_profile_picture():
    """Debug endpoint retained for backward compatibility."""
    # SECURITY: Only allow this endpoint in DEBUG mode to prevent information leakage
    if not current_app.config.get('DEBUG', False):
        abort(404)

    # Check if user likely uses Azure login (no password hash)
    uses_azure_login = current_user.password_hash is None

    debug_data = {
        'user_info': {
            'user_id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'has_password': current_user.password_hash is not None,
            'uses_azure_login': uses_azure_login,
        },
        'profile_picture': {
            'enabled': False,
            'message': 'Profile picture fields were removed; initials-based avatars are always used.'
        },
    }
    return json_ok(**debug_data)


@bp.route("/account-settings/devices/<int:device_id>/kickout", methods=["POST"])
@login_required
def kickout_own_device(device_id):
    """Kick out (end session) for user's own device. Keeps device registered."""
    try:
        from app.models.system import UserDevice

        # Verify device exists and belongs to current user
        device = UserDevice.query.filter_by(id=device_id, user_id=current_user.id).first_or_404()

        # Check if device is already logged out
        if device.logged_out_at:
            return json_bad_request(
                'Device is already logged out',
                success=False,
                error='Device is already logged out'
            )

        # Mark device as logged out
        device.logged_out_at = utcnow()
        db.session.flush()

        current_app.logger.info(
            f"User {current_user.id} kicked out their own device {device_id}"
        )

        return json_ok(message='Device session ended successfully')

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error kicking out device {device_id} for user {current_user.id}: {e}", exc_info=True)
        from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/account-settings/devices/<int:device_id>/remove", methods=["DELETE"])
@login_required
def remove_own_device(device_id):
    """Remove user's own device from the registry. Permanently deletes the device record."""
    try:
        from app.models.system import UserDevice

        # Verify device exists and belongs to current user
        device = UserDevice.query.filter_by(id=device_id, user_id=current_user.id).first_or_404()

        # Delete the device
        db.session.delete(device)
        db.session.flush()

        current_app.logger.info(
            f"User {current_user.id} removed their own device {device_id}"
        )

        return json_ok(message='Device removed successfully')

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error removing device {device_id} for user {current_user.id}: {e}", exc_info=True)
        return json_server_error('An internal error occurred.')
