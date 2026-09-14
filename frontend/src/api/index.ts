const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, data: any, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function fetchWithHandler(url: string, options: RequestInit = {}) {
  try {
    const response = await fetch(`${API_BASE_URL}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    // Handle 204 No Content
    if (response.status === 204) return null;

    const data = await response.json();

    if (!response.ok) {
      const message = data?.error?.message || data?.detail || 'An unexpected API error occurred';
      throw new ApiError(response.status, data, message);
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    
    // Network errors
    throw new ApiError(0, null, error instanceof Error ? error.message : 'Network error occurred');
  }
}

// ---------------------------------------------------------
// Services
// ---------------------------------------------------------

export const SystemService = {
  getHealth: () => fetchWithHandler('/health'),
  getStats: () => fetchWithHandler('/api/v1/stats'),
};

export const ConfigService = {
  getLocations: (page = 1, pageSize = 100) => 
    fetchWithHandler(`/api/v1/config/locations?page=${page}&page_size=${pageSize}`),
  getCategories: (page = 1, pageSize = 100) => 
    fetchWithHandler(`/api/v1/config/categories?page=${page}&page_size=${pageSize}`),
};

export const JobsService = {
  getJobs: (page = 1, pageSize = 100, status?: string) => {
    let url = `/api/v1/jobs?page=${page}&page_size=${pageSize}`;
    if (status) url += `&status=${status}`;
    return fetchWithHandler(url);
  },
  retryJob: (jobId: string) => fetchWithHandler(`/api/v1/jobs/${jobId}/retry`, { method: 'POST' }),
  retryAll: (status = 'FAILED') => fetchWithHandler(`/api/v1/jobs/retry-all?status=${status}`, { method: 'POST' }),
};

export const DiscoveryService = {
  getStatus: () => fetchWithHandler('/api/v1/discovery/status'),
  stopBatch: () => fetchWithHandler('/api/v1/discovery/stop', { method: 'POST' }),
};

export const BusinessesService = {
  getBusinesses: (params: Record<string, any> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        query.append(key, value.toString());
      }
    });
    return fetchWithHandler(`/api/v1/businesses?${query.toString()}`);
  },
  
  // Delegate CSV export entirely to the backend endpoint
  downloadCsv: (since?: string) => {
    let url = `${API_BASE_URL}/api/v1/export/businesses?format=csv`;
    if (since) url += `&since=${since}`;
    
    // Trigger download via standard browser behavior
    window.open(url, '_blank');
  }
};
