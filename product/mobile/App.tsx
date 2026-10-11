import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { api, API_BASE_URL, type ChatResponse, type Conversation, type ConversationDetail, type Message, type TokenResponse, type Usage } from './src/api';
import { t, type Language } from './src/i18n';

const TOKEN_KEY = 'omega.access-token';
const LANGUAGE_KEY = 'omega.language';
const DARK_KEY = 'omega.dark-mode';

function AppContent() {
  const [language, setLanguage] = useState<Language>('en');
  const [dark, setDark] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [lastFailedDraft, setLastFailedDraft] = useState('');
  const [usage, setUsage] = useState<Usage | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const rtl = language === 'ar';
  const compact = useWindowDimensions().width < 760;
  const colors = useMemo(() => dark
    ? { bg: '#0c111d', panel: '#141c2b', panel2: '#1c2638', text: '#f3f6fb', muted: '#a9b5c8', accent: '#74a7ff', border: '#28354a', danger: '#ff8f8f' }
    : { bg: '#f3f6fb', panel: '#ffffff', panel2: '#edf2fa', text: '#182235', muted: '#64748b', accent: '#315fe8', border: '#dce4f0', danger: '#b42318' }, [dark]);
  const styles = useMemo(() => makeStyles(colors, rtl, compact), [colors, rtl, compact]);

  const refreshConversations = useCallback(async (currentToken: string) => {
    const rows = await api<Conversation[]>('/api/v1/conversations', {}, currentToken);
    setConversations(rows);
    if (selectedId && !rows.some((row) => row.id === selectedId)) {
      setSelectedId(null);
      setMessages([]);
    }
  }, [selectedId]);

  const loadConversation = useCallback(async (id: string, currentToken: string) => {
    const detail = await api<ConversationDetail>(`/api/v1/conversations/${id}`, {}, currentToken);
    setSelectedId(detail.id);
    setMessages(detail.messages);
    setError('');
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [storedToken, storedLanguage, storedDark] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          AsyncStorage.getItem(LANGUAGE_KEY),
          AsyncStorage.getItem(DARK_KEY),
        ]);
        if (!alive) return;
        if (storedLanguage === 'en' || storedLanguage === 'ar') setLanguage(storedLanguage);
        setDark(storedDark === 'true');
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
    api<Conversation[]>('/api/v1/conversations', {}, token)
      .then((rows) => { if (alive) setConversations(rows); })
      .catch(async (cause: unknown) => {
        if (!alive) return;
        const message = cause instanceof Error ? cause.message : t(language, 'genericError');
        setError(message);
        if ((cause as { status?: number })?.status === 401) {
          await SecureStore.deleteItemAsync(TOKEN_KEY);
          if (alive) setToken(null);
        }
      });
    return () => { alive = false; };
  }, [token, language]);

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
        { method: 'POST', body: JSON.stringify({ content: text.trim() }) },
        token,
      );
      setMessages((previous) => [...previous, result.user_message, result.assistant_message]);
      setDraft('');
      setLastFailedDraft('');
      await refreshConversations(token);
      setSelectedId(conversation.id);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : t(language, 'genericError');
      setError(message);
      setLastFailedDraft(text);
    } finally {
      setBusy(false);
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

  const loadUsage = async () => {
    if (!token) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<Usage>('/api/v1/usage', {}, token);
      setUsage(result);
      setShowSettings(true);
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

  if (booting) {
    return <SafeAreaView style={[styles.screen, styles.center]}><ActivityIndicator size="large" color={colors.accent} /><Text style={styles.muted}>{t(language, 'loading')}</Text></SafeAreaView>;
  }

  if (!token) {
    return (
      <SafeAreaView style={styles.screen}>
        <StatusBar style={dark ? 'light' : 'dark'} />
        <View style={styles.authWrap}>
          <Text style={styles.brand}>ΩX</Text>
          <Text style={styles.title}>{t(language, 'appName')}</Text>
          <Text style={styles.muted}>{t(language, 'tagline')}</Text>
          <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" textContentType="emailAddress" placeholder={t(language, 'email')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'email')} />
          <TextInput value={password} onChangeText={setPassword} secureTextEntry textContentType={authMode === 'register' ? 'newPassword' : 'password'} placeholder={t(language, 'password')} placeholderTextColor={colors.muted} style={styles.input} accessibilityLabel={t(language, 'password')} />
          {authMode === 'register' && <Text style={styles.muted}>{t(language, 'registerHint')}</Text>}
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Button label={authMode === 'register' ? t(language, 'createAccount') : t(language, 'signIn')} onPress={handleAuth} disabled={busy || !email.trim() || !password} styles={styles} />
          <Pressable onPress={() => { setAuthMode(authMode === 'register' ? 'login' : 'register'); setError(''); }} accessibilityRole="button" style={styles.linkButton}>
            <Text style={styles.linkText}>{authMode === 'register' ? t(language, 'haveAccount') : t(language, 'needAccount')}</Text>
          </Pressable>
          <View style={[styles.row, styles.centerRow]}>
            <Button label={language === 'en' ? 'العربية' : 'English'} onPress={switchLanguage} small styles={styles} />
            <Button label={dark ? t(language, 'light') : t(language, 'dark')} onPress={switchTheme} small styles={styles} />
          </View>
        </View>
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
              <Text style={styles.brandSmall}>ΩX</Text>
              <View><Text style={styles.headerTitle}>{t(language, 'appName')}</Text><Text style={styles.connection}>{t(language, 'connection')}: {online ? t(language, 'connected') : t(language, 'disconnected')}</Text></View>
            </View>
            <View style={[styles.row, styles.headerActions]}>
              <Button label={language === 'en' ? 'عربي' : 'EN'} onPress={switchLanguage} small styles={styles} />
              <Button label={dark ? '☼' : '◐'} onPress={switchTheme} small styles={styles} />
              <Button label={t(language, 'signOut')} onPress={signOut} small styles={styles} />
            </View>
          </View>

          {!API_BASE_URL && <Text style={styles.warning}>{t(language, 'notConfigured')}</Text>}
          <View style={styles.content}>
            <View style={styles.sidebar}>
              <View style={[styles.row, styles.sectionHeader]}><Text style={styles.sectionTitle}>{t(language, 'conversations')}</Text><Button label="+" onPress={startNew} small styles={styles} /></View>
              <ScrollView style={styles.conversationScroll} contentContainerStyle={styles.conversationList}>
                {conversations.length === 0 ? <Text style={styles.muted}>{t(language, 'noConversations')}</Text> : conversations.map((item) => (
                  <Pressable key={item.id} onPress={() => token && loadConversation(item.id, token)} style={[styles.conversationItem, item.id === selectedId && styles.selectedConversation]} accessibilityRole="button" accessibilityLabel={item.title}>
                    <Text numberOfLines={1} style={styles.conversationTitle}>{item.title}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              <View style={styles.sidebarFooter}>
                <Button label={t(language, 'usage')} onPress={loadUsage} small styles={styles} />
                <Button label={t(language, 'settings')} onPress={() => setShowSettings((value) => !value)} small styles={styles} />
              </View>
              {showSettings && (
                <View style={styles.settingsCard}>
                  <Text style={styles.sectionTitle}>{t(language, 'settings')}</Text>
                  <Text style={styles.muted}>{t(language, 'language')}: {language === 'en' ? 'English' : 'العربية'}</Text>
                  <Text style={styles.muted}>{t(language, 'theme')}: {dark ? t(language, 'dark') : t(language, 'light')}</Text>
                  {usage && <Text style={styles.muted}>{t(language, 'usage')}: {usage.requests} requests · {usage.prompt_tokens + usage.completion_tokens} tokens</Text>}
                  {usage && <Text style={styles.muted}>{usage.note}</Text>}
                </View>
              )}
            </View>

            <View style={styles.chatPanel}>
              {compact && (
                <View style={[styles.mobileThreadBar, styles.row]}>
                  <Button label="+" onPress={startNew} small styles={styles} />
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.mobileThreadList}>
                    {conversations.map((item) => (
                      <Pressable key={item.id} onPress={() => token && loadConversation(item.id, token)} style={[styles.mobileThreadChip, item.id === selectedId && styles.selectedConversation]} accessibilityRole="button" accessibilityLabel={item.title}>
                        <Text numberOfLines={1} style={styles.conversationTitle}>{item.title}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                  <Button label={t(language, 'usage')} onPress={loadUsage} small styles={styles} />
                  <Button label={t(language, 'settings')} onPress={() => setShowSettings((value) => !value)} small styles={styles} />
                </View>
              )}
              {compact && showSettings && (
                <View style={styles.settingsCard}>
                  <Text style={styles.sectionTitle}>{t(language, 'settings')}</Text>
                  <Text style={styles.muted}>{t(language, 'language')}: {language === 'en' ? 'English' : 'العربية'}</Text>
                  <Text style={styles.muted}>{t(language, 'theme')}: {dark ? t(language, 'dark') : t(language, 'light')}</Text>
                  {usage && <Text style={styles.muted}>{t(language, 'usage')}: {usage.requests} requests · {usage.prompt_tokens + usage.completion_tokens} tokens</Text>}
                  {usage && <Text style={styles.muted}>{usage.note}</Text>}
                </View>
              )}
              <ScrollView style={styles.messages} contentContainerStyle={messages.length ? styles.messageList : styles.emptyState}>
                {messages.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyMark}>✳</Text>
                    <Text style={styles.title}>{t(language, 'emptyTitle')}</Text>
                    <Text style={styles.muted}>{t(language, 'emptyBody')}</Text>
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
              <Text style={styles.footnote}>{online ? 'Connected to backend API' : 'Backend connection unavailable'} · Model credentials remain server-side</Text>
            </View>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

type Styles = ReturnType<typeof makeStyles>;
function Button({ label, onPress, disabled = false, small = false, styles }: { label: string; onPress: () => void; disabled?: boolean; small?: boolean; styles: Styles }) {
  return <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled} style={[styles.button, small && styles.smallButton, disabled && styles.disabledButton]}><Text style={[styles.buttonText, disabled && styles.disabledText]}>{label}</Text></Pressable>;
}

function makeStyles(c: { bg: string; panel: string; panel2: string; text: string; muted: string; accent: string; border: string; danger: string }, rtl: boolean, compact: boolean) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bg },
    fill: { flex: 1 },
    center: { alignItems: 'center', justifyContent: 'center', gap: 12 },
    authWrap: { width: '100%', maxWidth: 460, alignSelf: 'center', padding: 24, gap: 14, flex: 1, justifyContent: 'center' },
    brand: { alignSelf: 'center', color: c.accent, fontSize: 48, fontWeight: '800' },
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
    header: { minHeight: 72, paddingHorizontal: 14, borderBottomWidth: 1, borderColor: c.border, justifyContent: 'space-between', backgroundColor: c.panel },
    brandLine: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
    brandSmall: { color: c.accent, fontSize: 24, fontWeight: '800' },
    headerTitle: { color: c.text, fontWeight: '700', fontSize: 15 },
    headerActions: { flexShrink: 0 },
    connection: { color: c.muted, fontSize: 11 },
    warning: { color: c.danger, backgroundColor: c.panel, padding: 10, textAlign: rtl ? 'right' : 'left' },
    content: { flex: 1, flexDirection: 'row' },
    sidebar: { width: 220, padding: 10, display: compact ? 'none' : 'flex', borderRightWidth: rtl ? 0 : 1, borderLeftWidth: rtl ? 1 : 0, borderColor: c.border, backgroundColor: c.panel },
    sectionHeader: { justifyContent: 'space-between', paddingVertical: 7 },
    sectionTitle: { color: c.text, fontSize: 14, fontWeight: '700', textAlign: rtl ? 'right' : 'left' },
    conversationScroll: { flex: 1 },
    conversationList: { gap: 6, paddingVertical: 8 },
    conversationItem: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 10, borderRadius: 10 },
    selectedConversation: { backgroundColor: c.panel2 },
    conversationTitle: { color: c.text, fontSize: 13, textAlign: rtl ? 'right' : 'left' },
    sidebarFooter: { gap: 6, paddingTop: 8, borderTopWidth: 1, borderColor: c.border },
    settingsCard: { backgroundColor: c.panel2, padding: 10, borderRadius: 10, marginTop: 8, gap: 5 },
    mobileThreadBar: { minHeight: 48, maxHeight: 52, paddingBottom: 6, borderBottomWidth: 1, borderColor: c.border },
    mobileThreadList: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 6, paddingHorizontal: 4 },
    mobileThreadChip: { height: 36, maxWidth: 160, justifyContent: 'center', paddingHorizontal: 10, borderRadius: 18, backgroundColor: c.panel },
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
  });
}

export default function App() {
  return <SafeAreaProvider><AppContent /></SafeAreaProvider>;
}
