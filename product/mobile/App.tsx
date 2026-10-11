import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  Share,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { api, API_BASE_URL, type ApiReadiness, type ChatResponse, type Conversation, type ConversationDetail, type Message, type ResponseMode, type TokenResponse, type Usage } from './src/api';
import { t, type CopyKey, type Language } from './src/i18n';
import ProjectsScreen from './src/ProjectsScreen';

type MainArea = 'chat' | 'projects' | 'agent' | 'browser' | 'terminal' | 'files' | 'usage' | 'diagnostics';

const TOKEN_KEY = 'omega.access-token';
const LANGUAGE_KEY = 'omega.language';
const DARK_KEY = 'omega.dark-mode';
const RESPONSE_MODE_KEY = 'omega.response-mode';
const RESPONSE_MODES: ResponseMode[] = ['balanced', 'explain', 'concise', 'writing', 'coding'];
const RESPONSE_MODE_LABELS: Record<ResponseMode, CopyKey> = {
  balanced: 'modeBalanced', explain: 'modeExplain', concise: 'modeConcise', writing: 'modeWriting', coding: 'modeCoding',
};

function AppContent() {
  const [language, setLanguage] = useState<Language>('en');
  const [dark, setDark] = useState(false);
  const [responseMode, setResponseMode] = useState<ResponseMode>('balanced');
  const [token, setToken] = useState<string | null>(null);
  const activeToken = useRef(token);
  useEffect(() => { activeToken.current = token; }, [token]);
  const [booting, setBooting] = useState(true);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchText, setSearchText] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [lastFailedDraft, setLastFailedDraft] = useState('');
  const [usage, setUsage] = useState<Usage | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [showNavigation, setShowNavigation] = useState(false);
  const [activeArea, setActiveArea] = useState<MainArea>('chat');
  const [readiness, setReadiness] = useState<ApiReadiness | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState('');
  const [diagnosticsBusy, setDiagnosticsBusy] = useState(false);
  const [editingConversation, setEditingConversation] = useState<Conversation | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  const rtl = language === 'ar';
  const compact = useWindowDimensions().width < 760;
  const colors = useMemo(() => dark
    ? { bg: '#0a1020', panel: '#101b2e', panel2: '#1a2a43', text: '#f5f8ff', muted: '#a2b3cc', accent: '#4f94ff', border: '#283a56', danger: '#ff8f8f' }
    : { bg: '#f4f7fc', panel: '#ffffff', panel2: '#eaf0f8', text: '#16253d', muted: '#647790', accent: '#2867d8', border: '#dce5f2', danger: '#b42318' }, [dark]);
  const styles = useMemo(() => makeStyles(colors, rtl, compact), [colors, rtl, compact]);

  const refreshConversations = useCallback(async (currentToken: string, query = '', isCurrent: () => boolean = () => true) => {
    const search = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
    const rows = await api<Conversation[]>(`/api/v1/conversations${search}`, {}, currentToken);
    if (!isCurrent() || activeToken.current !== currentToken) return;
    setConversations(rows);
    if (!query.trim() && selectedId && !rows.some((row) => row.id === selectedId)) {
      setSelectedId(null);
      setMessages([]);
    }
  }, [selectedId]);

  const loadConversation = useCallback(async (id: string, currentToken: string) => {
    try {
      const detail = await api<ConversationDetail>(`/api/v1/conversations/${id}`, {}, currentToken);
      if (activeToken.current !== currentToken) return;
      setSelectedId(detail.id);
      setMessages(detail.messages);
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    }
  }, [language]);

  const refreshReadiness = useCallback(async () => {
    setDiagnosticsBusy(true);
    setDiagnosticsError('');
    try {
      const result = await api<ApiReadiness>('/health/ready');
      setReadiness(result);
    } catch (cause) {
      setReadiness(null);
      setDiagnosticsError(cause instanceof Error ? cause.message : t(language, 'diagnosticsUnavailable'));
    } finally {
      setDiagnosticsBusy(false);
    }
  }, [language]);

  useEffect(() => { void refreshReadiness(); }, [refreshReadiness]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [storedToken, storedLanguage, storedDark, storedResponseMode] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          AsyncStorage.getItem(LANGUAGE_KEY),
          AsyncStorage.getItem(DARK_KEY),
          AsyncStorage.getItem(RESPONSE_MODE_KEY),
        ]);
        if (!alive) return;
        if (storedLanguage === 'en' || storedLanguage === 'ar') setLanguage(storedLanguage);
        setDark(storedDark === 'true');
        if (storedResponseMode && RESPONSE_MODES.includes(storedResponseMode as ResponseMode)) setResponseMode(storedResponseMode as ResponseMode);
        setToken(storedToken);
      } catch {
        if (alive) setError(t('en', 'genericError'));
      } finally {
        if (alive) setBooting(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!API_BASE_URL) {
      setOnline(false);
      return;
    }
    let alive = true;
    api<{ status: string }>('/health/live').then(() => alive && setOnline(true)).catch(() => alive && setOnline(false));
    return () => { alive = false; };
  }, [token]);

  useEffect(() => {
    if (!token) {
      setConversations([]);
      setSelectedId(null);
      setMessages([]);
      return;
    }
    let alive = true;
    refreshConversations(token, activeSearch, () => alive).catch(async (cause: unknown) => {
      if (!alive) return;
      const message = cause instanceof Error ? cause.message : t(language, 'genericError');
      setError(message);
      if ((cause as { status?: number })?.status === 401) {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        if (alive) setToken(null);
      }
    });
    return () => { alive = false; };
  }, [token, activeSearch, language, refreshConversations]);

  const handleAuth = async () => {
    setBusy(true);
    setError('');
    try {
      const path = authMode === 'register' ? '/api/v1/auth/register' : '/api/v1/auth/login';
      const result = await api<TokenResponse>(path, { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) });
      await SecureStore.setItemAsync(TOKEN_KEY, result.access_token);
      setToken(result.access_token);
      setPassword('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const createConversation = async (currentToken: string): Promise<Conversation> => {
    const row = await api<Conversation>('/api/v1/conversations', {
      method: 'POST', body: JSON.stringify({ title: t(language, 'newChat') }),
    }, currentToken);
    setConversations((previous) => [row, ...previous]);
    setSelectedId(row.id);
    setMessages([]);
    setError('');
    return row;
  };

  const sendMessage = async (text = draft) => {
    if (!token || !text.trim() || busy) return;
    setBusy(true);
    setError('');
    setLastFailedDraft('');
    try {
      const conversation = selectedId
        ? { id: selectedId }
        : await createConversation(token);
      const result = await api<ChatResponse>(
        `/api/v1/conversations/${conversation.id}/messages`,
        { method: 'POST', body: JSON.stringify({ content: text.trim(), response_mode: responseMode }) },
        token,
      );
      setMessages((previous) => [...previous, result.user_message, result.assistant_message]);
      setDraft('');
      setLastFailedDraft('');
      await refreshConversations(token, activeSearch);
      setSelectedId(conversation.id);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : t(language, 'genericError');
      setError(message);
      setLastFailedDraft(text);
    } finally {
      setBusy(false);
    }
  };

  const saveConversationTitle = async () => {
    if (!token || !editingConversation || !editingTitle.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const item = editingConversation;
      const renamed = await api<Conversation>(`/api/v1/conversations/${item.id}`, {
        method: 'PATCH', body: JSON.stringify({ title: editingTitle.trim() }),
      }, token);
      setConversations((previous) => previous.map((row) => row.id === renamed.id ? renamed : row));
      setEditingConversation(null);
      await refreshConversations(token, activeSearch);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const deleteConversation = async (item: Conversation) => {
    if (!token || busy) return;
    setBusy(true);
    setError('');
    try {
      await api<void>(`/api/v1/conversations/${item.id}`, { method: 'DELETE' }, token);
      setConversations((previous) => previous.filter((row) => row.id !== item.id));
      if (selectedId === item.id) {
        setSelectedId(null);
        setMessages([]);
      }
      await refreshConversations(token, activeSearch);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const showConversationActions = (item: Conversation) => Alert.alert(t(language, 'conversationOptions'), item.title, [
    { text: t(language, 'rename'), onPress: () => { setEditingTitle(item.title); setEditingConversation(item); } },
    {
      text: t(language, 'delete'),
      style: 'destructive',
      onPress: () => Alert.alert(t(language, 'deleteConversationTitle'), t(language, 'deleteConversationConfirm'), [
        { text: t(language, 'cancel'), style: 'cancel' },
        { text: t(language, 'delete'), style: 'destructive', onPress: () => { void deleteConversation(item); } },
      ]),
    },
    { text: t(language, 'cancel'), style: 'cancel' },
  ]);

  const toggleSettings = () => {
    const next = !showSettings;
    setShowSettings(next);
    if (next) void refreshReadiness();
  };

  const selectResponseMode = async (mode: ResponseMode) => {
    setResponseMode(mode);
    await AsyncStorage.setItem(RESPONSE_MODE_KEY, mode);
  };

  const shareConversation = async () => {
    if (!selectedId || !messages.length) return;
    const conversationTitle = conversations.find((item) => item.id === selectedId)?.title ?? t(language, 'appName');
    const transcript = messages.map((item) => `${item.role === 'user' ? (rtl ? 'أنت' : 'You') : 'ΩX'}\n${item.content}`).join('\n\n');
    try {
      await Share.share({ title: conversationTitle, message: `${conversationTitle}\n\n${transcript}` });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    }
  };

  const startNew = async () => {
    if (!token || busy) return;
    setBusy(true);
    setError('');
    try {
      await createConversation(token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    Alert.alert(t(language, 'signOut'), rtl ? 'هل تريد تسجيل الخروج؟' : 'Sign out of this account?', [
      { text: rtl ? 'إلغاء' : 'Cancel', style: 'cancel' },
      { text: t(language, 'signOut'), style: 'destructive', onPress: async () => {
        let revokeFailed = false;
        if (token) {
          try { await api<void>('/api/v1/auth/logout', { method: 'POST' }, token); }
          catch { revokeFailed = true; }
        }
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        setToken(null);
        setUsage(null);
        if (revokeFailed) Alert.alert(t(language, 'signOut'), rtl ? 'تم مسح هذا الجهاز. تعذر إبطال الجلسات الأخرى؛ ستنتهي صلاحية الرمز خلال ساعة.' : 'This device was signed out, but other sessions could not be revoked; the token expires within one hour.');
      } },
    ]);
  };

  const shareAccountExport = async () => {
    if (!token || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/account/export?max_bytes=500000`, {
        headers: { Accept: 'application/x-ndjson', Authorization: `Bearer ${token}` },
      });
      const declaredBytes = Number(response.headers.get('content-length') ?? 0);
      if (Number.isFinite(declaredBytes) && declaredBytes > 500_000) throw new Error(rtl ? 'النسخة كبيرة للمشاركة داخل التطبيق؛ استخدم نقطة التصدير الموثقة لتنزيلها.' : 'This export is too large to share in-app. Use the documented export endpoint to download it.');
      const body = await response.text();
      if (!response.ok) {
        let detail = `Request failed (${response.status}).`;
        try { detail = String((JSON.parse(body) as { detail?: unknown }).detail ?? detail); } catch { /* keep sanitized status */ }
        throw new Error(detail);
      }
      if (body.length > 500_000) throw new Error(rtl ? 'النسخة كبيرة للمشاركة داخل التطبيق؛ استخدم نقطة التصدير الموثقة لتنزيلها.' : 'This export is too large to share in-app. Use the documented export endpoint to download it.');
      await Share.share({ title: t(language, 'shareAccountData'), message: body });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const deleteMyAccount = async () => {
    if (!token || !deletePassword || busy) return;
    setBusy(true);
    setError('');
    try {
      await api<void>('/api/v1/account', {
        method: 'DELETE', body: JSON.stringify({ password: deletePassword }),
      }, token);
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      setToken(null);
      setConversations([]);
      setSelectedId(null);
      setMessages([]);
      setUsage(null);
      setDeletePassword('');
      setShowDeleteAccount(false);
      setShowSettings(false);
      Alert.alert(t(language, 'deleteAccount'), t(language, 'accountDeleted'));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const loadUsage = async () => {
    if (!token) return;
    setActiveArea('usage');
    setBusy(true);
    setError('');
    try {
      const result = await api<Usage>('/api/v1/usage', {}, token);
      setUsage(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const switchLanguage = async () => {
    const next: Language = language === 'en' ? 'ar' : 'en';
    setLanguage(next);
    await AsyncStorage.setItem(LANGUAGE_KEY, next);
  };

  const switchTheme = async () => {
    const next = !dark;
    setDark(next);
    await AsyncStorage.setItem(DARK_KEY, String(next));
  };

  const navigateTo = (area: MainArea | 'settings') => {
    if (area === 'settings') {
      toggleSettings();
      return;
    }
    setActiveArea(area);
    setError('');
    if (area === 'usage') void loadUsage();
    if (area === 'diagnostics') void refreshReadiness();
  };

  const navigationItems: { area: MainArea | 'settings'; label: CopyKey }[] = [
    { area: 'chat', label: 'navChat' },
    { area: 'projects', label: 'navProjects' },
    { area: 'agent', label: 'navAgent' },
    { area: 'browser', label: 'navBrowser' },
    { area: 'terminal', label: 'navTerminal' },
    { area: 'files', label: 'navFiles' },
    { area: 'usage', label: 'usage' },
    { area: 'diagnostics', label: 'navDiagnostics' },
    { area: 'settings', label: 'settings' },
  ];

  const diagnosticsContent = (
    <View style={styles.diagnosticsSection}>
      <Text style={styles.sectionTitle}>{t(language, 'settingsReady')}</Text>
      {diagnosticsBusy && <Text style={styles.muted}>{t(language, 'checking')}</Text>}
      {readiness && <>
        <Text style={styles.muted}>{t(language, 'connection')}: {readiness.status}</Text>
        <Text style={styles.muted}>{t(language, 'database')}: {readiness.database}</Text>
        <Text style={styles.muted}>{t(language, 'modelProvider')}: {readiness.model_provider_configured ? t(language, 'configured') : t(language, 'providerNotConfigured')}</Text>
        <Text style={styles.muted}>{t(language, 'model')}: {readiness.model || t(language, 'notSet')}</Text>
        <Text style={styles.sectionTitle}>{t(language, 'providerStatus')}</Text>
        <Text style={styles.muted}>{readiness.model_provider_configured ? t(language, 'providerConfiguredBody') : t(language, 'providerUnconfiguredBody')}</Text>
        {!readiness.model_provider_configured && <>
          <Text style={styles.sectionTitle}>{t(language, 'providerSetupTitle')}</Text>
          <Text style={styles.muted}>{t(language, 'providerSetupBody')}</Text>
        </>}
      </>}
      {diagnosticsError ? <Text style={styles.error}>{diagnosticsError}</Text> : null}
      <Button label={t(language, 'refresh')} onPress={() => { void refreshReadiness(); }} small styles={styles} />
    </View>
  );

  if (booting) {
    return <SafeAreaView style={[styles.screen, styles.center]}><ActivityIndicator size="large" color={colors.accent} /><Text style={styles.muted}>{t(language, 'loading')}</Text></SafeAreaView>;
  }

  if (!token) {
    return (
      <SafeAreaView style={styles.screen}>
        <StatusBar style={dark ? 'light' : 'dark'} />
        <ScrollView contentContainerStyle={styles.authScroll} keyboardShouldPersistTaps="handled">
          <View style={styles.authWrap}>
            <View style={[styles.row, styles.authTopBar]}>
              <View style={styles.brandLine}><Text style={styles.brandSmall}>ΩX</Text><Text style={styles.headerTitle}>{t(language, 'appName')}</Text></View>
              <View style={[styles.row, styles.authPreferences]}>
                <Button label={language === 'en' ? 'العربية' : 'English'} onPress={() => { void switchLanguage(); }} small styles={styles} />
                <Button label={dark ? t(language, 'light') : t(language, 'dark')} accessibilityLabel={dark ? t(language, 'light') : t(language, 'dark')} onPress={() => { void switchTheme(); }} small styles={styles} />
              </View>
            </View>
            <View style={styles.authCard}>
              <View style={styles.authMark}><Text style={styles.authMarkText}>ΩX</Text></View>
              <Text style={styles.eyebrow}>{t(language, 'tagline')}</Text>
              <Text style={styles.title}>{authMode === 'register' ? t(language, 'createAccountHeading') : t(language, 'welcomeBack')}</Text>
              <Text style={styles.muted}>{t(language, 'authSubheading')}</Text>
              <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" textContentType="emailAddress" placeholder={t(language, 'email')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'email')} />
              <TextInput value={password} onChangeText={setPassword} secureTextEntry textContentType={authMode === 'register' ? 'newPassword' : 'password'} placeholder={t(language, 'password')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'password')} />
              {authMode === 'register' && <Text style={styles.muted}>{t(language, 'registerHint')}</Text>}
              {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
              <Button label={authMode === 'register' ? t(language, 'createAccount') : t(language, 'signIn')} onPress={handleAuth} disabled={busy || !email.trim() || !password} styles={styles} />
              <Pressable onPress={() => { setAuthMode(authMode === 'register' ? 'login' : 'register'); setError(''); }} accessibilityRole="button" style={styles.linkButton}>
                <Text style={styles.linkText}>{authMode === 'register' ? t(language, 'haveAccount') : t(language, 'needAccount')}</Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen}>
        <StatusBar style={dark ? 'light' : 'dark'} />
        <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.header, styles.row]}>
            <View style={styles.brandLine}>
              {compact && <Pressable onPress={() => setShowNavigation(true)} accessibilityRole="button" accessibilityLabel={t(language, 'menu')} style={styles.menuButton}><Text style={styles.menuButtonText}>☰</Text></Pressable>}
              <Text style={styles.brandSmall}>ΩX</Text>
              <View><Text style={styles.headerTitle}>{t(language, 'appName')}</Text><Text style={styles.connection}>{t(language, 'connection')}: {online ? t(language, 'connected') : t(language, 'disconnected')}</Text></View>
            </View>
            <View style={[styles.row, styles.headerActions]}>
              {compact
                ? <Button label="+" accessibilityLabel={t(language, 'newChat')} onPress={startNew} small styles={styles} />
                : <>
                  <Button label={language === 'en' ? 'عربي' : 'EN'} onPress={switchLanguage} small styles={styles} />
                  <Button label={dark ? '☼' : '◐'} accessibilityLabel={dark ? t(language, 'light') : t(language, 'dark')} onPress={switchTheme} small styles={styles} />
                  <Button label={t(language, 'signOut')} onPress={signOut} disabled={busy} small styles={styles} />
                </>}
            </View>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.modeChipList}>
            {navigationItems.map((item) => (
              <Pressable key={item.area} onPress={() => navigateTo(item.area)} accessibilityRole="button" accessibilityState={{ selected: item.area === activeArea }} style={[styles.modeChip, item.area === activeArea && styles.selectedModeChip]}>
                <Text style={[styles.modeChipText, item.area === activeArea && styles.selectedModeChipText]}>{t(language, item.label)}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {!API_BASE_URL && <Text style={styles.warning}>{t(language, 'notConfigured')}</Text>}
          <View style={styles.content}>
          {activeArea === 'projects' ? readiness?.capabilities?.project_workspace
            ? <ProjectsScreen token={token} language={language} palette={colors} />
            : <View style={styles.chatPanel}><Text style={styles.title}>{t(language, 'unavailableFeatureTitle')}</Text><Text style={styles.sectionTitle}>{t(language, 'navProjects')}</Text><Text style={styles.muted}>{t(language, 'projectsUnavailableBody')}</Text></View>
            : activeArea === 'usage' ? <View style={styles.chatPanel}>
              <Text style={styles.title}>{t(language, 'usage')}</Text>
              {usage ? <>
                <Text style={styles.sectionTitle}>{usage.requests} requests</Text>
                <Text style={styles.muted}>{usage.prompt_tokens + usage.completion_tokens} tokens · {usage.prompt_tokens} input · {usage.completion_tokens} output</Text>
                <Text style={styles.muted}>{usage.note}</Text>
              </> : <Text style={styles.muted}>{error || t(language, 'diagnosticsUnavailable')}</Text>}
              <Button label={t(language, 'refresh')} onPress={() => { void loadUsage(); }} disabled={busy} small styles={styles} />
            </View>
            : activeArea === 'diagnostics' ? <View style={styles.chatPanel}>
              <Text style={styles.muted}>{t(language, 'diagnosticsBody')}</Text>{diagnosticsContent}
            </View>
            : activeArea === 'chat' ? <>
            <View style={styles.sidebar}>
              <View style={[styles.row, styles.sectionHeader]}><Text style={styles.sectionTitle}>{t(language, 'conversations')}</Text><Button label="+" accessibilityLabel={t(language, 'newChat')} onPress={startNew} small styles={styles} /></View>
              <View style={[styles.row, styles.searchRow]}>
                <TextInput value={searchText} onChangeText={setSearchText} onSubmitEditing={() => setActiveSearch(searchText.trim())} returnKeyType="search" placeholder={t(language, 'searchConversations')} placeholderTextColor={colors.muted} style={styles.searchInput} accessibilityLabel={t(language, 'searchConversations')} />
                <Button label={t(language, 'search')} onPress={() => setActiveSearch(searchText.trim())} small styles={styles} />
                {(searchText || activeSearch) ? <Button label={t(language, 'clearSearch')} onPress={() => { setSearchText(''); setActiveSearch(''); }} small styles={styles} /> : null}
              </View>
              <ScrollView style={styles.conversationScroll} contentContainerStyle={styles.conversationList}>
                {conversations.length === 0 ? <Text style={styles.muted}>{activeSearch ? t(language, 'noSearchResults') : t(language, 'noConversations')}</Text> : conversations.map((item) => (
                  <View key={item.id} style={styles.conversationRow}>
                    <Pressable onPress={() => token && loadConversation(item.id, token)} style={[styles.conversationItem, styles.conversationItemFlex, item.id === selectedId && styles.selectedConversation]} accessibilityRole="button" accessibilityLabel={item.title}>
                      <Text numberOfLines={1} style={styles.conversationTitle}>{item.title}</Text>
                    </Pressable>
                    <Pressable onPress={() => showConversationActions(item)} style={styles.actionIcon} accessibilityRole="button" accessibilityLabel={t(language, 'conversationOptions')}>
                      <Text style={styles.actionIconText}>⋯</Text>
                    </Pressable>
                  </View>
                ))}
              </ScrollView>
              <View style={styles.sidebarFooter}>
                <Button label={t(language, 'usage')} onPress={loadUsage} small styles={styles} />
                <Button label={t(language, 'settings')} onPress={toggleSettings} small styles={styles} />
              </View>
            </View>

            <View style={styles.chatPanel}>
              {readiness?.capabilities?.response_modes && <View style={styles.toolsPanel}>
                <Text style={styles.sectionTitle}>{t(language, 'responseMode')}</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.modeChipList}>
                  {RESPONSE_MODES.map((mode) => (
                    <Pressable key={mode} onPress={() => { void selectResponseMode(mode); }} accessibilityRole="button" accessibilityState={{ selected: responseMode === mode }} accessibilityLabel={t(language, RESPONSE_MODE_LABELS[mode])} style={[styles.modeChip, responseMode === mode && styles.selectedModeChip]}>
                      <Text style={[styles.modeChipText, responseMode === mode && styles.selectedModeChipText]}>{t(language, RESPONSE_MODE_LABELS[mode])}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
              </View>}
              <View style={[styles.row, styles.shareBar]}>
                <Button label={t(language, 'shareConversation')} onPress={() => { void shareConversation(); }} disabled={!selectedId || messages.length === 0} small styles={styles} />
              </View>
              <ScrollView style={styles.messages} contentContainerStyle={messages.length ? styles.messageList : styles.emptyState}>
                {messages.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyMark}>✳</Text>
                    <Text style={styles.title}>{t(language, 'emptyTitle')}</Text>
                    <Text style={styles.muted}>{t(language, 'emptyBody')}</Text>
                    <Text style={styles.sectionTitle}>{t(language, 'quickStarts')}</Text>
                    <View style={styles.suggestionList}>
                      {(['quickExplain', 'quickPlan', 'quickDraft'] as const).map((key) => (
                        <Pressable key={key} onPress={() => setDraft(t(language, key))} accessibilityRole="button" style={styles.suggestionChip}>
                          <Text style={styles.suggestionText}>{t(language, key)}</Text>
                        </Pressable>
                      ))}
                    </View>
                    {conversations.length === 0 && <Button label={t(language, 'newChat')} onPress={startNew} styles={styles} />}
                  </View>
                ) : messages.map((item) => (
                  <View key={item.id} style={[styles.messageBubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
                    <Text style={styles.messageRole}>{item.role === 'user' ? (rtl ? 'أنت' : 'You') : 'ΩX'}</Text>
                    <Text selectable style={styles.messageText}>{item.content}</Text>
                  </View>
                ))}
                {busy && <View style={[styles.messageBubble, styles.assistantBubble, styles.row]}><ActivityIndicator color={colors.accent} /><Text style={styles.muted}> {t(language, 'loading')}</Text></View>}
              </ScrollView>
              {error ? <View style={styles.errorBox}><Text accessibilityRole="alert" style={styles.error}>{error}</Text>{lastFailedDraft ? <Button label={t(language, 'retry')} onPress={() => sendMessage(lastFailedDraft)} small styles={styles} /> : <Button label={t(language, 'retry')} onPress={() => token && refreshConversations(token).catch((cause) => setError(cause.message))} small styles={styles} />}</View> : null}
              <View style={[styles.composer, styles.row]}>
                <TextInput value={draft} onChangeText={setDraft} multiline maxLength={20000} placeholder={t(language, 'messagePlaceholder')} placeholderTextColor={colors.muted} style={styles.composerInput} accessibilityLabel={t(language, 'messagePlaceholder')} onSubmitEditing={() => sendMessage()} />
                <Button label={t(language, 'send')} onPress={() => sendMessage()} disabled={busy || !draft.trim()} styles={styles} />
              </View>
              <Text style={styles.footnote}>{online ? 'Connected to backend API' : 'Backend connection unavailable'} · Provider credentials stay server-side</Text>
            </View>
            </>
            : <View style={styles.chatPanel}>
              <Text style={styles.title}>{t(language, 'unavailableFeatureTitle')}</Text>
              <Text style={styles.sectionTitle}>{t(language, activeArea === 'agent' ? 'navAgent' : activeArea === 'browser' ? 'navBrowser' : activeArea === 'terminal' ? 'navTerminal' : 'navFiles')}</Text>
              <Text style={styles.muted}>{t(language, activeArea === 'agent' ? 'agentUnavailableBody' : activeArea === 'browser' ? 'browserUnavailableBody' : activeArea === 'terminal' ? 'terminalUnavailableBody' : 'filesUnavailableBody')}</Text>
              {activeArea === 'files' ? <Button label={t(language, 'navProjects')} onPress={() => setActiveArea('projects')} small styles={styles} /> : null}
            </View>}
          </View>
        </KeyboardAvoidingView>
        <Modal visible={compact && showNavigation} transparent animationType="fade" onRequestClose={() => setShowNavigation(false)}>
          <View style={styles.drawerBackdrop}>
            <Pressable style={styles.drawerScrim} onPress={() => setShowNavigation(false)} accessibilityRole="button" accessibilityLabel={t(language, 'close')} />
            <View style={[styles.drawerPanel, rtl ? styles.drawerPanelRTL : styles.drawerPanelLTR]}>
              <View style={[styles.row, styles.drawerHeader]}>
                <View style={styles.brandLine}><Text style={styles.brandSmall}>ΩX</Text><Text style={styles.headerTitle}>{t(language, 'conversations')}</Text></View>
                <Button label={t(language, 'close')} onPress={() => setShowNavigation(false)} small styles={styles} />
              </View>
              <Button label={`+  ${t(language, 'newChat')}`} onPress={() => { setShowNavigation(false); void startNew(); }} styles={styles} />
              <View style={[styles.row, styles.drawerSearchRow]}>
                <TextInput value={searchText} onChangeText={setSearchText} onSubmitEditing={() => setActiveSearch(searchText.trim())} returnKeyType="search" placeholder={t(language, 'searchConversations')} placeholderTextColor={colors.muted} style={styles.searchInput} accessibilityLabel={t(language, 'searchConversations')} />
                <Button label={t(language, 'search')} onPress={() => setActiveSearch(searchText.trim())} small styles={styles} />
              </View>
              {(searchText || activeSearch) ? <Button label={t(language, 'clearSearch')} onPress={() => { setSearchText(''); setActiveSearch(''); }} small styles={styles} /> : null}
              <Text style={styles.sectionTitle}>{activeSearch ? t(language, 'searchResults') : t(language, 'recentConversations')}</Text>
              <ScrollView style={styles.drawerList} contentContainerStyle={styles.conversationList}>
                {conversations.length === 0 ? <Text style={styles.muted}>{activeSearch ? t(language, 'noSearchResults') : t(language, 'noConversations')}</Text> : conversations.map((item) => (
                  <View key={item.id} style={styles.conversationRow}>
                    <Pressable onPress={() => { if (token) void loadConversation(item.id, token); setShowNavigation(false); }} style={[styles.conversationItem, styles.conversationItemFlex, item.id === selectedId && styles.selectedConversation]} accessibilityRole="button" accessibilityLabel={item.title}>
                      <Text numberOfLines={1} style={styles.conversationTitle}>{item.title}</Text>
                    </Pressable>
                    <Pressable onPress={() => showConversationActions(item)} style={styles.actionIcon} accessibilityRole="button" accessibilityLabel={t(language, 'conversationOptions')}>
                      <Text style={styles.actionIconText}>⋯</Text>
                    </Pressable>
                  </View>
                ))}
              </ScrollView>
              <View style={styles.drawerFooter}>
                <View style={[styles.row, styles.drawerFooterRow]}>
                  <Button label={t(language, 'usage')} onPress={() => { setShowNavigation(false); void loadUsage(); }} small styles={styles} />
                  <Button label={t(language, 'settings')} onPress={() => { setShowNavigation(false); toggleSettings(); }} small styles={styles} />
                </View>
                <View style={[styles.row, styles.drawerFooterRow]}>
                  <Button label={language === 'en' ? 'العربية' : 'English'} onPress={() => { void switchLanguage(); }} small styles={styles} />
                  <Button label={dark ? t(language, 'light') : t(language, 'dark')} onPress={() => { void switchTheme(); }} small styles={styles} />
                </View>
                <Button label={t(language, 'signOut')} onPress={() => { setShowNavigation(false); signOut(); }} disabled={busy} small styles={styles} />
              </View>
            </View>
          </View>
        </Modal>
        <Modal visible={showSettings} transparent animationType="slide" onRequestClose={() => setShowSettings(false)}>
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalCard, styles.settingsModal]}>
              <View style={[styles.row, styles.settingsModalHeader]}>
                <Text style={styles.sectionTitle}>{t(language, 'settings')}</Text>
                <Button label={t(language, 'close')} onPress={() => setShowSettings(false)} small styles={styles} />
              </View>
              <ScrollView style={styles.settingsModalBody} contentContainerStyle={styles.settingsModalContent}>
                <View style={[styles.row, styles.settingsRow]}><Text style={styles.settingsLabel}>{t(language, 'language')}</Text><Button label={language === 'en' ? 'العربية' : 'English'} onPress={() => { void switchLanguage(); }} small styles={styles} /></View>
                <View style={[styles.row, styles.settingsRow]}><Text style={styles.settingsLabel}>{t(language, 'theme')}</Text><Button label={dark ? t(language, 'light') : t(language, 'dark')} onPress={() => { void switchTheme(); }} small styles={styles} /></View>
                {usage && <Text style={styles.muted}>{t(language, 'usage')}: {usage.requests} requests · {usage.prompt_tokens + usage.completion_tokens} tokens</Text>}
                {usage && <Text style={styles.muted}>{usage.note}</Text>}
                {(readiness?.capabilities?.account_export || readiness?.capabilities?.account_deletion) && <View style={styles.diagnosticsSection}>
                  <Text style={styles.sectionTitle}>{t(language, 'privacyTitle')}</Text>
                  {readiness.capabilities?.account_export && <Button label={t(language, 'shareAccountData')} onPress={() => { void shareAccountExport(); }} disabled={busy} small styles={styles} />}
                  {readiness.capabilities?.account_deletion && <Button label={t(language, 'deleteAccount')} onPress={() => { setDeletePassword(''); setShowDeleteAccount(true); }} disabled={busy} small styles={styles} />}
                </View>}
                {diagnosticsContent}
              </ScrollView>
            </View>
          </View>
        </Modal>
        <Modal visible={!!editingConversation} transparent animationType="fade" onRequestClose={() => setEditingConversation(null)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.sectionTitle}>{t(language, 'renameConversation')}</Text>
              <TextInput value={editingTitle} onChangeText={setEditingTitle} maxLength={120} autoFocus placeholder={t(language, 'renameConversation')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'renameConversation')} />
              <View style={[styles.row, styles.modalActions]}>
                <Button label={t(language, 'cancel')} onPress={() => setEditingConversation(null)} small styles={styles} />
                <Button label={t(language, 'save')} onPress={() => { void saveConversationTitle(); }} disabled={busy || !editingTitle.trim()} small styles={styles} />
              </View>
            </View>
          </View>
        </Modal>
        <Modal visible={showDeleteAccount} transparent animationType="fade" onRequestClose={() => { setShowDeleteAccount(false); setDeletePassword(''); }}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.sectionTitle}>{t(language, 'confirmDeleteAccount')}</Text>
              <Text style={styles.muted}>{t(language, 'deleteAccountWarning')}</Text>
              <TextInput value={deletePassword} onChangeText={setDeletePassword} secureTextEntry textContentType="password" placeholder={t(language, 'currentPassword')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'currentPassword')} />
              {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
              <View style={[styles.row, styles.modalActions]}>
                <Button label={t(language, 'cancel')} onPress={() => { setShowDeleteAccount(false); setDeletePassword(''); }} disabled={busy} small styles={styles} />
                <Button label={t(language, 'confirmDeleteAccount')} onPress={() => { void deleteMyAccount(); }} disabled={busy || !deletePassword} small styles={styles} />
              </View>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

type Styles = ReturnType<typeof makeStyles>;
function Button({ label, onPress, disabled = false, small = false, accessibilityLabel, styles }: { label: string; onPress: () => void; disabled?: boolean; small?: boolean; accessibilityLabel?: string; styles: Styles }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel ?? label} onPress={onPress} disabled={disabled} style={[styles.button, small && styles.smallButton, disabled && styles.disabledButton]}><Text style={[styles.buttonText, disabled && styles.disabledText]}>{label}</Text></Pressable>;
}

function makeStyles(c: { bg: string; panel: string; panel2: string; text: string; muted: string; accent: string; border: string; danger: string }, rtl: boolean, compact: boolean) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bg },
    fill: { flex: 1 },
    center: { alignItems: 'center', justifyContent: 'center', gap: 12 },
    authScroll: { flexGrow: 1, justifyContent: 'center' },
    authWrap: { width: '100%', maxWidth: 520, alignSelf: 'center', paddingHorizontal: 22, paddingVertical: 24, gap: 18 },
    authTopBar: { justifyContent: 'space-between' },
    authPreferences: { gap: 6 },
    authCard: { backgroundColor: c.panel, borderWidth: 1, borderColor: c.border, borderRadius: 22, padding: 24, gap: 14, shadowColor: '#071427', shadowOpacity: 0.08, shadowRadius: 22, shadowOffset: { width: 0, height: 10 }, elevation: 3 },
    authMark: { width: 58, height: 58, borderRadius: 19, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' },
    authMarkText: { color: '#ffffff', fontSize: 22, fontWeight: '900' },
    eyebrow: { color: c.accent, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 },
    title: { color: c.text, fontSize: 24, fontWeight: '700', textAlign: rtl ? 'right' : 'left' },
    muted: { color: c.muted, fontSize: 14, lineHeight: 21, textAlign: rtl ? 'right' : 'left' },
    input: { minHeight: 50, backgroundColor: c.panel, borderWidth: 1, borderColor: c.border, borderRadius: 12, color: c.text, paddingHorizontal: 14, textAlign: rtl ? 'right' : 'left' },
    button: { minHeight: 46, justifyContent: 'center', alignItems: 'center', backgroundColor: c.accent, borderRadius: 12, paddingHorizontal: 16 },
    smallButton: { minHeight: 40, paddingHorizontal: 12, borderRadius: 10 },
    buttonText: { color: '#ffffff', fontSize: 14, fontWeight: '700' },
    disabledButton: { backgroundColor: c.panel2, opacity: 0.75 },
    disabledText: { color: c.muted },
    linkButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
    linkText: { color: c.accent, fontSize: 14, fontWeight: '600' },
    row: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 8 },
    centerRow: { justifyContent: 'center' },
    header: { minHeight: compact ? 64 : 72, paddingHorizontal: compact ? 10 : 14, borderBottomWidth: 1, borderColor: c.border, justifyContent: 'space-between', backgroundColor: c.panel },
    brandLine: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
    menuButton: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: c.panel2 },
    menuButtonText: { color: c.text, fontSize: 20, fontWeight: '700' },
    brandSmall: { color: c.accent, fontSize: 24, fontWeight: '800' },
    headerTitle: { color: c.text, fontWeight: '700', fontSize: 15 },
    headerActions: { flexShrink: 0 },
    connection: { color: c.muted, fontSize: 11 },
    warning: { color: c.danger, backgroundColor: c.panel, padding: 10, textAlign: rtl ? 'right' : 'left' },
    content: { flex: 1, flexDirection: rtl ? 'row-reverse' : 'row' },
    sidebar: { width: 220, padding: 10, display: compact ? 'none' : 'flex', borderRightWidth: rtl ? 0 : 1, borderLeftWidth: rtl ? 1 : 0, borderColor: c.border, backgroundColor: c.panel },
    sectionHeader: { justifyContent: 'space-between', paddingVertical: 7 },
    sectionTitle: { color: c.text, fontSize: 14, fontWeight: '700', textAlign: rtl ? 'right' : 'left' },
    searchRow: { paddingVertical: 6, flexWrap: 'wrap' },
    searchInput: { flex: 1, minWidth: 72, minHeight: 40, backgroundColor: c.panel2, borderWidth: 1, borderColor: c.border, borderRadius: 10, color: c.text, paddingHorizontal: 8, fontSize: 12, textAlign: rtl ? 'right' : 'left' },
    conversationScroll: { flex: 1 },
    conversationList: { gap: 6, paddingVertical: 8 },
    conversationRow: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 4 },
    conversationItemFlex: { flex: 1, minWidth: 0 },
    conversationItem: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 10, borderRadius: 10 },
    actionIcon: { width: 32, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 8, backgroundColor: c.panel2 },
    actionIconText: { color: c.accent, fontSize: 20, fontWeight: '700', lineHeight: 22 },
    selectedConversation: { backgroundColor: c.panel2 },
    conversationTitle: { color: c.text, fontSize: 13, textAlign: rtl ? 'right' : 'left' },
    sidebarFooter: { gap: 6, paddingTop: 8, borderTopWidth: 1, borderColor: c.border },
    settingsCard: { backgroundColor: c.panel2, padding: 10, borderRadius: 10, marginTop: 8, gap: 5 },
    diagnosticsSection: { borderTopWidth: 1, borderColor: c.border, marginTop: 8, paddingTop: 8, gap: 5 },
    toolsPanel: { gap: 5, paddingTop: 4 },
    shareBar: { justifyContent: 'flex-end', minHeight: 36, paddingTop: 4 },
    settingsModal: { maxHeight: '82%' },
    settingsModalHeader: { justifyContent: 'space-between' },
    settingsModalBody: { flexShrink: 1, maxHeight: 620 },
    settingsModalContent: { gap: 5, paddingBottom: 2 },
    settingsRow: { justifyContent: 'space-between', minHeight: 48, borderBottomWidth: 1, borderColor: c.border, paddingVertical: 4 },
    settingsLabel: { color: c.text, fontSize: 14, fontWeight: '600' },
    drawerBackdrop: { flex: 1, justifyContent: 'flex-start' },
    drawerScrim: { ...StyleSheet.absoluteFill, backgroundColor: '#00000088' },
    drawerPanel: { width: '86%', maxWidth: 360, height: '100%', backgroundColor: c.panel, padding: 14, gap: 10, borderColor: c.border },
    drawerPanelLTR: { alignSelf: 'flex-start', borderRightWidth: 1 },
    drawerPanelRTL: { alignSelf: 'flex-end', borderLeftWidth: 1 },
    drawerHeader: { justifyContent: 'space-between', minHeight: 44 },
    drawerSearchRow: { gap: 6 },
    drawerList: { flex: 1, minHeight: 100 },
    drawerFooter: { gap: 8, borderTopWidth: 1, borderColor: c.border, paddingTop: 10 },
    drawerFooterRow: { justifyContent: 'space-between' },
    suggestionList: { gap: 6, width: '100%' },
    suggestionChip: { minHeight: 40, justifyContent: 'center', borderRadius: 12, paddingHorizontal: 12, backgroundColor: c.panel2, borderWidth: 1, borderColor: c.border },
    suggestionText: { color: c.text, fontSize: 13, textAlign: rtl ? 'right' : 'left' },
    modeChipList: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 6, paddingHorizontal: 2 },
    modeChip: { minHeight: 34, justifyContent: 'center', paddingHorizontal: 10, borderRadius: 17, borderWidth: 1, borderColor: c.border, backgroundColor: c.panel },
    selectedModeChip: { backgroundColor: c.accent, borderColor: c.accent },
    modeChipText: { color: c.text, fontSize: 12, fontWeight: '600' },
    selectedModeChipText: { color: '#ffffff' },
    chatPanel: { flex: 1, padding: 12, minWidth: 0 },
    messages: { flex: 1 },
    messageList: { gap: 12, paddingVertical: 8 },
    emptyState: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 12 },
    emptyCard: { maxWidth: 460, gap: 12, alignItems: 'center', padding: 18, backgroundColor: c.panel, borderRadius: 18, borderWidth: 1, borderColor: c.border },
    emptyMark: { color: c.accent, fontSize: 38 },
    messageBubble: { maxWidth: '92%', padding: 12, borderRadius: 14, gap: 6 },
    userBubble: { alignSelf: rtl ? 'flex-start' : 'flex-end', backgroundColor: c.accent },
    assistantBubble: { alignSelf: rtl ? 'flex-end' : 'flex-start', backgroundColor: c.panel, borderWidth: 1, borderColor: c.border },
    messageRole: { color: c.muted, fontSize: 11, fontWeight: '700' },
    messageText: { color: c.text, fontSize: 15, lineHeight: 23, textAlign: rtl ? 'right' : 'left' },
    composer: { alignItems: 'flex-end', backgroundColor: c.panel, borderColor: c.border, borderWidth: 1, borderRadius: 14, padding: 8, marginTop: 8 },
    composerInput: { flex: 1, maxHeight: 130, minHeight: 42, color: c.text, paddingHorizontal: 8, paddingVertical: 9, textAlign: rtl ? 'right' : 'left', textAlignVertical: 'center' },
    footnote: { color: c.muted, fontSize: 10, textAlign: 'center', paddingTop: 6 },
    error: { color: c.danger, fontSize: 13, textAlign: rtl ? 'right' : 'left', flexShrink: 1 },
    errorBox: { paddingHorizontal: 6, paddingVertical: 8, gap: 8 },
    modalBackdrop: { flex: 1, backgroundColor: '#00000088', justifyContent: 'center', alignItems: 'center', padding: 20 },
    modalCard: { width: '100%', maxWidth: 440, backgroundColor: c.panel, borderColor: c.border, borderWidth: 1, borderRadius: 16, padding: 18, gap: 14 },
    modalActions: { justifyContent: 'flex-end', flexWrap: 'wrap' },
  });
}

export default function App() {
  return <SafeAreaProvider><AppContent /></SafeAreaProvider>;
}
