const DEFAULT_OAUTH_ERROR_MESSAGE =
  "Something went wrong during authentication. Please try again.";

type OAuthMessageBuilder = (providerName: string) => string;

const OAUTH_ERROR_MESSAGE_BUILDERS: Record<string, OAuthMessageBuilder> = {
  existing_account: (providerName) =>
    `An account with this email already exists via ${providerName}. Please sign in with ${providerName} instead, or use a different account.`,
  consent_denied: () => "Login was cancelled. You can try again whenever you're ready.",
  code_expired: () => "The login session expired. Please try again.",
  email_not_verified: (providerName) =>
    `Your ${providerName} email is not verified. Please verify it and try again.`,
  no_email: (providerName) =>
    `We couldn't retrieve an email from ${providerName}. Make sure your email is public or try a different provider.`,
  csrf_failed: () => "Login could not be verified (security check failed). Please try again.",
  invalid_provider: () => "Invalid login provider. Please try again.",
  missing_code: () => "Login did not complete. Please try again.",
  not_authenticated: () => "You must be signed in to perform this action.",
  provider_conflict: () => "This provider is already linked to another account.",
};

function getProviderDisplayName(provider: string | null | undefined): string {
  if (!provider) {
    return "another provider";
  }
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

export function getOAuthErrorMessage(
  code: string | null | undefined,
  provider?: string | null,
): string {
  if (!code) {
    return DEFAULT_OAUTH_ERROR_MESSAGE;
  }

  const buildMessage = OAUTH_ERROR_MESSAGE_BUILDERS[code];
  if (!buildMessage) {
    return DEFAULT_OAUTH_ERROR_MESSAGE;
  }

  return buildMessage(getProviderDisplayName(provider));
}

export { DEFAULT_OAUTH_ERROR_MESSAGE };
