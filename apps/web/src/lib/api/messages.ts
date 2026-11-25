import { ApiError } from "./client";

export function formatWait(seconds: number | undefined): string {
  if (seconds === undefined || seconds <= 0) return "a few minutes";
  if (seconds < 60) return "a minute";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 120) return `${minutes} minutes`;
  return `${Math.ceil(minutes / 60)} hours`;
}

/**
 * User-facing wording for API failures. Names the problem and the way out, and never echoes
 * anything that could confirm whether an account exists (login says the same thing for an
 * unknown email and a wrong password).
 */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  if (error.status === 0) return error.message;
  if (error.status === 429) {
    return `Too many attempts. Try again in ${formatWait(error.retryAfterSeconds)}.`;
  }
  switch (error.code) {
    case "invalid_credentials":
      return "Email or password is incorrect.";
    case "email_not_verified":
      return "Verify your email address to continue.";
    case "invalid_token":
      return "This link is invalid or has expired.";
    case "last_owner":
      return "An organization must keep at least one owner.";
    case "already_member":
      return "That person is already a member.";
    case "forbidden":
      return "You don't have permission to do that.";
    case "duplicate_document":
      return "This exact file was already uploaded to this chatbot.";
    case "unsupported_media_type":
      return "That file type is not supported. Upload a PDF, DOCX or TXT file.";
    case "file_too_large":
      return "That file is too large.";
    case "already_processing":
      return "That is already being processed.";
    case "storage_unavailable":
      return "File storage is unavailable right now. Try again in a moment.";
    case "blocked_destination":
      return "Only public websites can be crawled. That address is not allowed.";
    case "chatbot_name_taken":
      return "A chatbot with this name already exists. Choose another name.";
    case "plan_limit_reached":
      return error.message;
    case "org_restricted":
      return "This organization is read-only right now.";
    case "validation_error":
      return "Some fields need attention.";
    case "not_found":
      return "That doesn't exist, or you don't have access to it.";
    case "service_unavailable":
      return "The service is busy. Try again in a moment.";
    default:
      return error.status >= 500 ? "Something went wrong on our side. Try again." : error.message;
  }
}
