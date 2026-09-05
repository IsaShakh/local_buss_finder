export type ApiErrorBody = {
  error: {
    code: string;
    detail: string;
    fields: Record<string, string[]>;
  };
};

export class ApiClientError extends Error {
  readonly code: string;
  readonly fields: Record<string, string[]>;
  readonly status: number;

  constructor(body: ApiErrorBody, status: number) {
    super(body.error.detail);
    this.name = 'ApiClientError';
    this.code = body.error.code;
    this.fields = body.error.fields;
    this.status = status;
  }
}

export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) {
    return false;
  }

  const error = value.error;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'detail' in error &&
    typeof error.detail === 'string' &&
    'fields' in error &&
    typeof error.fields === 'object' &&
    error.fields !== null
  );
}
