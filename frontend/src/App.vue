<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  Activity,
  AlertTriangle,
  Bold,
  CheckCircle2,
  Clock3,
  FilePlus2,
  Highlighter,
  Italic,
  Loader2,
  LogIn,
  LogOut,
  MessageSquarePlus,
  Underline,
  UserRound,
  RefreshCw,
  Search,
  ShieldAlert,
  X
} from 'lucide-vue-next';
import {
  addIncidentUpdate,
  clearCsrfToken,
  createReporter,
  createIncident,
  getCurrentUser,
  getIncident,
  getApiErrorMessage,
  getLoginUrl,
  isForbiddenError,
  isUnauthorizedError,
  listReporters,
  listIncidents,
  logout,
  refreshCsrfToken,
  resolveIncident
} from '@/services/incidents';
import type { AuthUser, Incident, IncidentCreatePayload, IncidentDetail, Reporter, Severity } from '@/types';

const severities: Severity[] = ['low', 'medium', 'high', 'critical'];

const incidents = ref<Incident[]>([]);
const reporters = ref<Reporter[]>([]);
const selectedIncident = ref<IncidentDetail | null>(null);
const selectedId = ref<number | null>(null);
const pagination = reactive({
  limit: 50,
  offset: 0,
  total: 0
});
const isLoading = ref(false);
const isDetailLoading = ref(false);
const isSubmitting = ref(false);
const error = ref('');
const authError = ref('');
const authState = reactive({
  isAuthenticated: false,
  user: null as AuthUser | null,
  role: 'readonly',
  isLoading: true
});
const searchTerm = ref('');
const filters = reactive({
  status: '',
  severity: '',
  createdFrom: '',
  createdTo: ''
});
const form = reactive<IncidentCreatePayload>({
  title: '',
  created_by: '',
  severity: 'low',
  description: ''
});
const updateMessage = ref('');
const newReporterName = ref('');
const descriptionInput = ref<HTMLTextAreaElement | null>(null);

const openIncidents = computed(() => incidents.value.filter((incident) => incident.status === 'open'));
const resolvedIncidents = computed(() => incidents.value.filter((incident) => incident.status === 'resolved'));
const criticalIncidents = computed(() =>
  incidents.value.filter((incident) => ['critical', 'high'].includes(incident.severity.toLowerCase()))
);

const filteredIncidents = computed(() => {
  const term = searchTerm.value.trim().toLowerCase();
  if (!term) return incidents.value;

  return incidents.value.filter((incident) =>
    [incident.title, incident.created_by, incident.description, incident.severity, incident.status, String(incident.id)]
      .join(' ')
      .toLowerCase()
      .includes(term)
  );
});

const latestActivity = computed(() => {
  const dates = incidents.value.map((incident) => new Date(incident.created_at).getTime());
  const latest = Math.max(...dates);
  return Number.isFinite(latest) ? formatRelative(new Date(latest).toISOString()) : 'No activity';
});
const currentPage = computed(() => Math.floor(pagination.offset / pagination.limit) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil(pagination.total / pagination.limit)));
const canGoPrevious = computed(() => pagination.offset > 0);
const canGoNext = computed(() => pagination.offset + pagination.limit < pagination.total);
const displayUserName = computed(() => authState.user?.display_name || authState.user?.email || 'Signed in');
const canCreateRecords = computed(() =>
  authState.isAuthenticated && ['admin', 'manager', 'responder', 'reporter'].includes(authState.role)
);
const canManageIncident = computed(() =>
  authState.isAuthenticated && ['admin', 'manager', 'responder'].includes(authState.role)
);

async function loadAuth(): Promise<void> {
  authState.isLoading = true;
  authError.value = '';

  try {
    const user = await getCurrentUser();
    await refreshCsrfToken();
    authState.user = user;
    authState.role = user.role;
    authState.isAuthenticated = true;
  } catch (caught) {
    clearCsrfToken();
    authState.user = null;
    authState.role = 'readonly';
    authState.isAuthenticated = false;
    if (!isUnauthorizedError(caught)) {
      authError.value = getErrorMessage(caught, 'Could not load sign-in state.');
    }
  } finally {
    authState.isLoading = false;
  }
}

function login(): void {
  window.location.assign(getLoginUrl());
}

async function logoutUser(): Promise<void> {
  authState.isLoading = true;
  authError.value = '';

  try {
    await logout();
  } catch (caught) {
    if (!isUnauthorizedError(caught)) {
      authError.value = getErrorMessage(caught, 'Could not sign out.');
    }
  } finally {
    clearCsrfToken();
    authState.user = null;
    authState.role = 'readonly';
    authState.isAuthenticated = false;
    authState.isLoading = false;
  }
}

async function loadIncidents(preferredId?: number): Promise<void> {
  isLoading.value = true;
  error.value = '';

  try {
    const response = await listIncidents({
      status: filters.status || undefined,
      severity: filters.severity || undefined,
      created_from: filters.createdFrom || undefined,
      created_to: filters.createdTo || undefined,
      limit: pagination.limit,
      offset: pagination.offset
    });
    incidents.value = response.items;
    pagination.total = response.pagination.total;

    const nextId = preferredId ?? selectedId.value ?? incidents.value[0]?.id ?? null;
    if (nextId) {
      await selectIncident(nextId);
    } else {
      selectedIncident.value = null;
      selectedId.value = null;
    }
  } catch (caught) {
    error.value = getErrorMessage(caught, 'Could not load incidents.');
  } finally {
    isLoading.value = false;
  }
}

async function loadReporters(): Promise<void> {
  try {
    reporters.value = await listReporters();
  } catch (caught) {
    error.value = getErrorMessage(caught, 'Could not load saved reporters.');
  }
}

async function submitReporter(): Promise<void> {
  if (!canCreateRecords.value) return;
  const name = newReporterName.value.trim();
  if (!name) return;

  isSubmitting.value = true;
  error.value = '';

  try {
    const reporter = await createReporter(name);
    await loadReporters();
    form.created_by = reporter.name;
    newReporterName.value = '';
  } catch (caught) {
    if (isUnauthorizedError(caught) || isForbiddenError(caught)) {
      await loadAuth();
    }
    error.value = getErrorMessage(caught, 'Could not save reporter.');
  } finally {
    isSubmitting.value = false;
  }
}

async function selectIncident(id: number): Promise<void> {
  selectedId.value = id;
  isDetailLoading.value = true;

  try {
    selectedIncident.value = await getIncident(id);
  } catch (caught) {
    error.value = getErrorMessage(caught, 'Could not load incident details.');
  } finally {
    isDetailLoading.value = false;
  }
}

async function submitIncident(): Promise<void> {
  if (!canCreateRecords.value) return;
  if (!form.title.trim() || !form.created_by.trim() || !form.description.trim()) return;

  isSubmitting.value = true;
  error.value = '';

  try {
    const created = await createIncident({
      title: form.title.trim(),
      created_by: form.created_by.trim(),
      severity: form.severity,
      description: form.description.trim()
    });
    form.title = '';
    form.created_by = '';
    form.severity = 'low';
    form.description = '';
    await loadIncidents(created.id);
  } catch (caught) {
    if (isUnauthorizedError(caught) || isForbiddenError(caught)) {
      await loadAuth();
    }
    error.value = getErrorMessage(caught, 'Could not create the incident.');
  } finally {
    isSubmitting.value = false;
  }
}

async function submitUpdate(): Promise<void> {
  if (!canManageIncident.value) return;
  if (!selectedIncident.value || !updateMessage.value.trim()) return;

  isSubmitting.value = true;
  error.value = '';

  try {
    await addIncidentUpdate(selectedIncident.value.id, updateMessage.value.trim());
    updateMessage.value = '';
    await selectIncident(selectedIncident.value.id);
  } catch (caught) {
    if (isUnauthorizedError(caught) || isForbiddenError(caught)) {
      await loadAuth();
    }
    error.value = getErrorMessage(caught, 'Could not add the update.');
  } finally {
    isSubmitting.value = false;
  }
}

async function markResolved(): Promise<void> {
  if (!canManageIncident.value) return;
  if (!selectedIncident.value) return;

  isSubmitting.value = true;
  error.value = '';

  try {
    const resolved = await resolveIncident(selectedIncident.value.id);
    await loadIncidents(resolved.id);
  } catch (caught) {
    if (isUnauthorizedError(caught) || isForbiddenError(caught)) {
      await loadAuth();
    }
    error.value = getErrorMessage(caught, 'Could not resolve the incident.');
  } finally {
    isSubmitting.value = false;
  }
}

function clearFilters(): void {
  searchTerm.value = '';
  filters.status = '';
  filters.severity = '';
  filters.createdFrom = '';
  filters.createdTo = '';
  pagination.offset = 0;
  void loadIncidents();
}

function applyServerFilters(): void {
  pagination.offset = 0;
  void loadIncidents();
}

function previousPage(): void {
  if (!canGoPrevious.value) return;
  pagination.offset = Math.max(0, pagination.offset - pagination.limit);
  void loadIncidents();
}

function nextPage(): void {
  if (!canGoNext.value) return;
  pagination.offset += pagination.limit;
  void loadIncidents();
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(value));
}

function formatRelative(value: string): string {
  const diffMs = Date.now() - new Date(value).getTime();
  const diffMins = Math.max(1, Math.round(diffMs / 60000));
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.round(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

function renderRichText(value: string): string {
  const lines = value.replace(/\r\n/g, '\n').split('\n');
  const output: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const closeList = (): void => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      closeList();
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/);
    const numberedMatch = line.match(/^\d+[.)]\s+(.+)$/);

    if (bulletMatch) {
      if (listType !== 'ul') {
        closeList();
        output.push('<ul>');
        listType = 'ul';
      }
      output.push(`<li>${renderInlineText(bulletMatch[1])}</li>`);
      continue;
    }

    if (numberedMatch) {
      if (listType !== 'ol') {
        closeList();
        output.push('<ol>');
        listType = 'ol';
      }
      output.push(`<li>${renderInlineText(numberedMatch[1])}</li>`);
      continue;
    }

    closeList();
    output.push(`<p>${renderInlineText(line)}</p>`);
  }

  closeList();
  return output.join('');
}

function renderInlineText(value: string): string {
  const linkPlaceholders: string[] = [];
  let rendered = escapeHtml(value).replace(/\bhttps?:\/\/[^\s<]+/g, (url) => {
    const placeholder = `%%LINK_${linkPlaceholders.length}%%`;
    linkPlaceholders.push(url);
    return placeholder;
  });

  rendered = rendered.replace(/==(.+?)==/g, '<mark>$1</mark>');
  rendered = rendered.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  rendered = rendered.replace(/__(.+?)__/g, '<u>$1</u>');
  rendered = rendered.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, '$1<em>$2</em>');

  return rendered.replace(/%%LINK_(\d+)%%/g, (_match, index) => {
    const url = linkPlaceholders[Number(index)];
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
  });
}

function applyDescriptionFormat(prefix: string, suffix = prefix): void {
  const input = descriptionInput.value;
  if (!input) return;

  const start = input.selectionStart;
  const end = input.selectionEnd;
  const selectedText = form.description.slice(start, end);
  const fallbackText = getFormattingFallback(prefix);
  const textToWrap = selectedText || fallbackText;

  form.description = [
    form.description.slice(0, start),
    prefix,
    textToWrap,
    suffix,
    form.description.slice(end)
  ].join('');

  requestAnimationFrame(() => {
    input.focus();
    const selectionStart = start + prefix.length;
    const selectionEnd = selectionStart + textToWrap.length;
    input.setSelectionRange(selectionStart, selectionEnd);
  });
}

function getFormattingFallback(prefix: string): string {
  const fallbacks: Record<string, string> = {
    '**': 'bold text',
    '*': 'italic text',
    '__': 'underlined text',
    '==': 'highlighted text'
  };

  return fallbacks[prefix] ?? 'formatted text';
}

function escapeHtml(value: string): string {
  const replacements: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };

  return value.replace(/[&<>"']/g, (character) => replacements[character]);
}

function getErrorMessage(caught: unknown, fallback: string): string {
  return getApiErrorMessage(caught, fallback);
}

onMounted(() => {
  void loadAuth();
  void loadReporters();
  void loadIncidents();
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><ShieldAlert :size="24" /></div>
        <div>
          <p>Incident Command</p>
          <span>Operations desk</span>
        </div>
      </div>

      <form class="create-panel" @submit.prevent="submitIncident">
        <div class="panel-title">
          <FilePlus2 :size="18" />
          <h2>New Incident</h2>
        </div>
        <template v-if="canCreateRecords">
          <label>
            <span>Title</span>
            <input v-model="form.title" required maxlength="120" placeholder="Payment gateway latency" />
          </label>
          <div class="reporter-picker">
            <label>
              <span>Reported by</span>
              <select v-model="form.created_by" required>
                <option value="" disabled>Select saved name</option>
                <option v-for="reporter in reporters" :key="reporter.id" :value="reporter.name">
                  {{ reporter.name }}
                </option>
              </select>
            </label>
            <div class="reporter-form">
              <input v-model="newReporterName" maxlength="120" placeholder="Save new name" />
              <button
                class="mini-action"
                type="button"
                :disabled="isSubmitting || !newReporterName.trim()"
                @click="submitReporter"
              >
                Save
              </button>
            </div>
          </div>
          <label>
            <span>Severity</span>
            <select v-model="form.severity">
              <option v-for="severity in severities" :key="severity" :value="severity">
                {{ severity }}
              </option>
            </select>
          </label>
          <label>
            <span>Description</span>
            <div class="format-toolbar" aria-label="Description formatting tools">
              <button type="button" title="Bold" @click="applyDescriptionFormat('**')">
                <Bold :size="16" />
              </button>
              <button type="button" title="Italic" @click="applyDescriptionFormat('*')">
                <Italic :size="16" />
              </button>
              <button type="button" title="Underline" @click="applyDescriptionFormat('__')">
                <Underline :size="16" />
              </button>
              <button type="button" title="Highlight" @click="applyDescriptionFormat('==')">
                <Highlighter :size="16" />
              </button>
            </div>
            <textarea
              ref="descriptionInput"
              v-model="form.description"
              required
              rows="6"
              placeholder="What happened?
- Impacted service
- Customer impact
https://status.example.com"
            />
          </label>
          <button class="primary-action" :disabled="isSubmitting">
            <Loader2 v-if="isSubmitting" class="spin" :size="18" />
            <FilePlus2 v-else :size="18" />
            Create
          </button>
        </template>
        <div v-else class="auth-callout">
          <p v-if="authState.isAuthenticated">Your current role is readonly. Write actions are hidden.</p>
          <p v-else>Sign in to create incidents or add operational updates.</p>
          <button v-if="!authState.isAuthenticated" class="primary-action" type="button" @click="login">
            <LogIn :size="18" />
            Sign in
          </button>
        </div>
      </form>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <h1>Incident Reporting</h1>
          <p>Track open issues, capture updates, and close the loop.</p>
        </div>
        <div class="topbar-actions">
          <div class="auth-status">
            <span v-if="authState.isLoading">Checking sign-in</span>
            <template v-else-if="authState.isAuthenticated">
              <strong>{{ displayUserName }}</strong>
              <span>{{ authState.role }}</span>
            </template>
            <span v-else>Not signed in</span>
          </div>
          <button
            v-if="authState.isAuthenticated"
            class="auth-button"
            type="button"
            :disabled="authState.isLoading"
            @click="logoutUser"
          >
            <LogOut :size="18" />
            Logout
          </button>
          <button v-else class="auth-button" type="button" :disabled="authState.isLoading" @click="login">
            <LogIn :size="18" />
            Login
          </button>
          <button class="icon-button" title="Refresh incidents" @click="loadIncidents()" :disabled="isLoading">
            <RefreshCw :class="{ spin: isLoading }" :size="19" />
          </button>
        </div>
      </header>

      <section class="metrics-grid">
        <article class="metric">
          <Activity :size="20" />
          <span>Open on page</span>
          <strong>{{ openIncidents.length }}</strong>
        </article>
        <article class="metric">
          <AlertTriangle :size="20" />
          <span>High Priority on page</span>
          <strong>{{ criticalIncidents.length }}</strong>
        </article>
        <article class="metric">
          <CheckCircle2 :size="20" />
          <span>Resolved on page</span>
          <strong>{{ resolvedIncidents.length }}</strong>
        </article>
        <article class="metric">
          <Clock3 :size="20" />
          <span>Latest on page</span>
          <strong>{{ latestActivity }}</strong>
        </article>
      </section>

      <section class="content-grid">
        <div class="incident-list">
          <div class="toolbar">
            <div class="search-field">
              <Search :size="18" />
              <input v-model="searchTerm" placeholder="Search incidents" />
            </div>
            <select v-model="filters.status" @change="applyServerFilters">
              <option value="">All status</option>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
            </select>
            <select v-model="filters.severity" @change="applyServerFilters">
              <option value="">All severity</option>
              <option v-for="severity in severities" :key="severity" :value="severity">
                {{ severity }}
              </option>
            </select>
            <label class="date-box" :class="{ filled: filters.createdFrom }">
              <span>From</span>
              <input v-model="filters.createdFrom" type="date" title="From date" @change="applyServerFilters" />
            </label>
            <label class="date-box" :class="{ filled: filters.createdTo }">
              <span>To</span>
              <input v-model="filters.createdTo" type="date" title="To date" @change="applyServerFilters" />
            </label>
            <button class="icon-button" title="Clear filters" @click="clearFilters">
              <X :size="18" />
            </button>
          </div>

          <div v-if="authError" class="notice error">{{ authError }}</div>
          <div v-if="authState.isAuthenticated && authState.role === 'readonly'" class="notice info">
            You are signed in with readonly access. Create, update, and resolve actions are hidden.
          </div>
          <div v-if="error" class="notice error">{{ error }}</div>

          <div v-if="isLoading" class="loading-state">
            <Loader2 class="spin" :size="24" />
            <span>Loading incidents</span>
          </div>

          <div v-else-if="!filteredIncidents.length" class="empty-state">
            <ShieldAlert :size="28" />
            <h2>No incidents found</h2>
            <p>Adjust the filters or create a new report from the left panel.</p>
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Incident</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="incident in filteredIncidents"
                  :key="incident.id"
                  :class="{ selected: incident.id === selectedId }"
                  @click="selectIncident(incident.id)"
                >
                  <td>#{{ incident.id }}</td>
                  <td>
                    <strong>{{ incident.title }}</strong>
                    <span>By {{ incident.created_by }} - {{ incident.description }}</span>
                  </td>
                  <td><span class="badge" :class="`severity-${incident.severity}`">{{ incident.severity }}</span></td>
                  <td><span class="badge" :class="`status-${incident.status}`">{{ incident.status }}</span></td>
                  <td>{{ formatRelative(incident.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="!isLoading && pagination.total" class="pagination-bar">
            <span>
              Page {{ currentPage }} of {{ totalPages }} · {{ pagination.total }} total
            </span>
            <div>
              <button class="pager-action" type="button" :disabled="!canGoPrevious" @click="previousPage">
                Previous
              </button>
              <button class="pager-action" type="button" :disabled="!canGoNext" @click="nextPage">
                Next
              </button>
            </div>
          </div>
        </div>

        <aside class="detail-panel">
          <div v-if="isDetailLoading" class="loading-state">
            <Loader2 class="spin" :size="24" />
            <span>Loading detail</span>
          </div>

          <template v-else-if="selectedIncident">
            <div class="detail-header">
              <div>
                <span class="eyebrow">Incident #{{ selectedIncident.id }}</span>
                <h2>{{ selectedIncident.title }}</h2>
              </div>
              <span class="badge" :class="`status-${selectedIncident.status}`">{{ selectedIncident.status }}</span>
            </div>

            <div class="detail-meta">
              <span class="badge" :class="`severity-${selectedIncident.severity}`">{{ selectedIncident.severity }}</span>
              <span class="reporter"><UserRound :size="15" /> {{ selectedIncident.created_by }}</span>
              <span>{{ formatDate(selectedIncident.created_at) }}</span>
            </div>

            <div class="rich-text description" v-html="renderRichText(selectedIncident.description)" />

            <button
              v-if="selectedIncident.status !== 'resolved' && canManageIncident"
              class="resolve-action"
              :disabled="isSubmitting"
              @click="markResolved"
            >
              <CheckCircle2 :size="18" />
              Resolve
            </button>

            <div class="updates">
              <h3>Updates</h3>
              <ol v-if="selectedIncident.updates.length">
                <li v-for="update in selectedIncident.updates" :key="update.id">
                  <span>{{ formatDate(update.created_at) }}</span>
                  <div class="rich-text update-message" v-html="renderRichText(update.message)" />
                </li>
              </ol>
              <p v-else class="muted">No updates have been recorded yet.</p>
            </div>

            <form v-if="canManageIncident" class="update-form" @submit.prevent="submitUpdate">
              <label>
                <span>Add update</span>
                <textarea
                  v-model="updateMessage"
                  rows="4"
                  placeholder="Add notes, links, or bullet points."
                />
              </label>
              <button class="secondary-action" :disabled="isSubmitting || !updateMessage.trim()">
                <MessageSquarePlus :size="18" />
                Add Update
              </button>
            </form>
            <p v-else-if="authState.isAuthenticated" class="muted">Your role cannot add updates or resolve incidents.</p>
            <p v-else class="muted">Sign in as a responder or admin to add updates or resolve incidents.</p>
          </template>

          <div v-else class="empty-state">
            <ShieldAlert :size="28" />
            <h2>Select an incident</h2>
            <p>Choose an incident from the table to see the timeline and actions.</p>
          </div>
        </aside>
      </section>
    </main>
  </div>
</template>
