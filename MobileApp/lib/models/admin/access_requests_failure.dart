/// User-visible access-requests errors; map to [AppLocalizations] in the UI layer.
sealed class AccessRequestsFailure {
  const AccessRequestsFailure();
}

/// Network or transport failure loading the list.
final class AccessRequestsFailureLoad extends AccessRequestsFailure {
  const AccessRequestsFailureLoad();
}

/// HTTP 403 when loading the list.
final class AccessRequestsFailureViewForbidden extends AccessRequestsFailure {
  const AccessRequestsFailureViewForbidden();
}

/// Success envelope indicated failure or malformed success payload.
final class AccessRequestsFailureUnexpectedResponse extends AccessRequestsFailure {
  const AccessRequestsFailureUnexpectedResponse();
}

/// Approve/reject failed (network, non-403/400 errors, or empty 400 body).
final class AccessRequestsFailureAction extends AccessRequestsFailure {
  const AccessRequestsFailureAction();
}

/// HTTP 403 on approve/reject.
final class AccessRequestsFailureActionForbidden extends AccessRequestsFailure {
  const AccessRequestsFailureActionForbidden();
}

/// Server-supplied message (e.g. HTTP 400 body); may already be localized by API.
final class AccessRequestsFailureServerMessage extends AccessRequestsFailure {
  final String message;

  const AccessRequestsFailureServerMessage(this.message);
}
