/**
 * Wrapper for API requests to add CSRF headers and handle errors.
 */

const getCsrfToken = () => {
    // If we have a meta tag or cookie, but for now we might get it from a request
    // Since Flask WTForms sets a CSRF token in session, we need to send it back.
    // In our security.py, we expect X-CSRF-Token in headers if session exists.
    // Let's read from a cookie if possible, or assume it's attached to the window object.
    return window.CSRF_TOKEN || '';
};

export const api = {
    async request(url, options = {}) {
        const headers = { ...options.headers };
        
        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
        
        // Add CSRF token for mutating requests
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            headers['X-CSRF-Token'] = getCsrfToken();
        }

        const response = await fetch(url, {
            ...options,
            headers
        });

        if (response.status === 401) {
            // Unauthorized, redirect to login
            if (window.location.pathname !== '/login') {
                window.location.href = '/login';
            }
            throw new Error('Não autorizado');
        }

        const data = await response.json().catch(() => null);

        if (!response.ok) {
            const msg = data?.error || data?.message || 'Erro no servidor';
            throw new Error(msg);
        }

        return data;
    },

    get(url) {
        return this.request(url, { method: 'GET' });
    },

    post(url, body) {
        return this.request(url, { method: 'POST', body: JSON.stringify(body) });
    },

    put(url, body) {
        return this.request(url, { method: 'PUT', body: JSON.stringify(body) });
    },

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
};
