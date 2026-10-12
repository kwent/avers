// Empties the throwaway test collection, so later flows start from zero.
for (const item of json(http.get(`${API_URL}/collection`).body).items)
  http.request(`${API_URL}/collection/${item.id}`, { method: 'DELETE' });
