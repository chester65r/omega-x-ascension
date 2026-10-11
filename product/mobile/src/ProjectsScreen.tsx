import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { api, type Project, type ProjectCheckpoint, type ProjectDiff, type ProjectFile, type ProjectFileSummary } from './api';
import { t, type Language } from './i18n';

type Palette = { bg: string; panel: string; panel2: string; text: string; muted: string; accent: string; border: string; danger: string };
type Props = { token: string; language: Language; palette: Palette };

export default function ProjectsScreen({ token, language, palette }: Props) {
  const rtl = language === 'ar';
  const styles = useMemo(() => makeStyles(palette, rtl), [palette, rtl]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [files, setFiles] = useState<ProjectFileSummary[]>([]);
  const [checkpoints, setCheckpoints] = useState<ProjectCheckpoint[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileRevision, setFileRevision] = useState<number | null>(null);
  const [projectName, setProjectName] = useState('');
  const [newFilePath, setNewFilePath] = useState('README.md');
  const [diff, setDiff] = useState<ProjectDiff | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refreshProjects = useCallback(async () => {
    const result = await api<Project[]>('/api/v1/projects', {}, token);
    setProjects(result);
    if (selectedProject && !result.some((item) => item.id === selectedProject.id)) setSelectedProject(null);
  }, [selectedProject, token]);

  const refreshFiles = useCallback(async (projectId: string) => {
    const result = await api<ProjectFileSummary[]>(`/api/v1/projects/${projectId}/files`, {}, token);
    setFiles(result);
  }, [token]);

  const refreshCheckpoints = useCallback(async (projectId: string) => {
    const result = await api<ProjectCheckpoint[]>(`/api/v1/projects/${projectId}/checkpoints`, {}, token);
    setCheckpoints(result);
  }, [token]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api<Project[]>('/api/v1/projects', {}, token)
      .then((result) => { if (alive) setProjects(result); })
      .catch((cause: unknown) => { if (alive) setError(cause instanceof Error ? cause.message : t(language, 'genericError')); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [language, token]);

  const openProject = async (project: Project) => {
    setSelectedProject(project);
    setSelectedFile(null);
    setFileContent('');
    setFileRevision(null);
    setDiff(null);
    setError('');
    setBusy(true);
    try {
      await Promise.all([refreshFiles(project.id), refreshCheckpoints(project.id)]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const createProject = async () => {
    if (!projectName.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const created = await api<Project>('/api/v1/projects', {
        method: 'POST', body: JSON.stringify({ name: projectName.trim(), description: '' }),
      }, token);
      setProjects((current) => [created, ...current]);
      setProjectName('');
      setNotice(t(language, 'projectCreated'));
      await openProject(created);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const openFile = async (filePath: string) => {
    if (!selectedProject) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const file = await api<ProjectFile>(`/api/v1/projects/${selectedProject.id}/files/${encodeURIComponent(filePath)}`, {}, token);
      setSelectedFile(file.path);
      setFileContent(file.content);
      setFileRevision(file.revision);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const createFile = async () => {
    if (!selectedProject || !newFilePath.trim() || busy) return;
    const filePath = newFilePath.trim();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const file = await api<ProjectFile>(`/api/v1/projects/${selectedProject.id}/files/${encodeURIComponent(filePath)}`, {
        method: 'PUT', body: JSON.stringify({ content: '' }),
      }, token);
      setSelectedFile(file.path);
      setFileContent(file.content);
      setFileRevision(file.revision);
      setNewFilePath('');
      await refreshFiles(selectedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const saveFile = async () => {
    if (!selectedProject || !selectedFile || fileRevision === null || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const file = await api<ProjectFile>(`/api/v1/projects/${selectedProject.id}/files/${encodeURIComponent(selectedFile)}`, {
        method: 'PUT', body: JSON.stringify({ content: fileContent, expected_revision: fileRevision }),
      }, token);
      setFileRevision(file.revision);
      setNotice(t(language, 'fileSaved'));
      await refreshFiles(selectedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const saveCheckpoint = async () => {
    if (!selectedProject || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api<ProjectCheckpoint>(`/api/v1/projects/${selectedProject.id}/checkpoints`, {
        method: 'POST', body: JSON.stringify({ label: rtl ? 'نقطة حفظ من الجوال' : 'Mobile checkpoint' }),
      }, token);
      await refreshCheckpoints(selectedProject.id);
      setNotice(t(language, 'checkpointSaved'));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const showCheckpointDiff = async (checkpoint: ProjectCheckpoint) => {
    if (!selectedProject || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<ProjectDiff>(`/api/v1/projects/${selectedProject.id}/diff?checkpoint_id=${encodeURIComponent(checkpoint.id)}`, {}, token);
      setDiff(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
    } finally {
      setBusy(false);
    }
  };

  const deleteFile = () => {
    if (!selectedProject || !selectedFile || busy) return;
    Alert.alert(t(language, 'delete'), `${t(language, 'deleteProjectFileConfirm')}\n\n${selectedFile}`, [
      { text: t(language, 'cancel'), style: 'cancel' },
      { text: t(language, 'delete'), style: 'destructive', onPress: async () => {
        setBusy(true);
        setError('');
        try {
          await api<void>(`/api/v1/projects/${selectedProject.id}/files/${encodeURIComponent(selectedFile)}`, { method: 'DELETE' }, token);
          setSelectedFile(null);
          setFileContent('');
          setFileRevision(null);
          await refreshFiles(selectedProject.id);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
        } finally {
          setBusy(false);
        }
      } },
    ]);
  };

  const deleteProject = () => {
    if (!selectedProject || busy) return;
    Alert.alert(t(language, 'delete'), `${t(language, 'deleteProjectConfirm')}\n\n${selectedProject.name}`, [
      { text: t(language, 'cancel'), style: 'cancel' },
      { text: t(language, 'delete'), style: 'destructive', onPress: async () => {
        setBusy(true);
        setError('');
        try {
          await api<void>(`/api/v1/projects/${selectedProject.id}`, { method: 'DELETE' }, token);
          setSelectedProject(null);
          setSelectedFile(null);
          setFiles([]);
          setCheckpoints([]);
          setDiff(null);
          await refreshProjects();
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : t(language, 'genericError'));
        } finally {
          setBusy(false);
        }
      } },
    ]);
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>{t(language, 'navProjects')}</Text>
      <Text style={styles.body}>{t(language, 'workspaceIntro')}</Text>
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}
      {loading ? <View style={styles.inline}><ActivityIndicator color={palette.accent} /><Text style={styles.muted}>{t(language, 'loading')}</Text></View> : null}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>{t(language, 'createProjectHeading')}</Text>
        <View style={styles.inline}>
          <TextInput value={projectName} onChangeText={setProjectName} maxLength={80} placeholder={t(language, 'projectName')} placeholderTextColor={palette.muted} style={styles.input} accessibilityLabel={t(language, 'projectName')} />
          <Pressable onPress={() => { void createProject(); }} disabled={busy || !projectName.trim()} accessibilityRole="button" style={[styles.button, (busy || !projectName.trim()) && styles.disabled]}><Text style={styles.buttonText}>{t(language, 'createProject')}</Text></Pressable>
        </View>
      </View>
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>{t(language, 'projectList')}</Text>
        {!loading && projects.length === 0 ? <Text style={styles.muted}>{t(language, 'noProjects')}</Text> : null}
        {projects.map((project) => (
          <Pressable key={project.id} onPress={() => { void openProject(project); }} accessibilityRole="button" accessibilityState={{ selected: project.id === selectedProject?.id }} style={[styles.projectRow, project.id === selectedProject?.id && styles.selectedRow]}>
            <View style={styles.fill}><Text style={styles.projectName}>{project.name}</Text><Text style={styles.muted}>{project.description || t(language, 'noProjectDescription')}</Text></View>
            <Text style={styles.muted}>›</Text>
          </Pressable>
        ))}
      </View>
      {selectedProject ? <View style={styles.card}>
        <View style={styles.sectionHeader}>
          <View style={styles.fill}><Text style={styles.sectionTitle}>{selectedProject.name}</Text><Text style={styles.muted}>{rtl ? `عدد الملفات: ${files.length}` : `${files.length} files`}</Text></View>
          <Pressable onPress={deleteProject} accessibilityRole="button" style={styles.dangerButton}><Text style={styles.dangerText}>{t(language, 'delete')}</Text></Pressable>
        </View>
        <View style={styles.inline}>
          <TextInput value={newFilePath} onChangeText={setNewFilePath} maxLength={512} autoCapitalize="none" autoCorrect={false} placeholder={t(language, 'newFilePath')} placeholderTextColor={palette.muted} style={styles.input} accessibilityLabel={t(language, 'newFilePath')} />
          <Pressable onPress={() => { void createFile(); }} disabled={busy || !newFilePath.trim()} accessibilityRole="button" style={[styles.button, (busy || !newFilePath.trim()) && styles.disabled]}><Text style={styles.buttonText}>{t(language, 'createFile')}</Text></Pressable>
        </View>
        {files.length === 0 ? <Text style={styles.muted}>{t(language, 'noProjectFiles')}</Text> : null}
        {files.map((file) => (
          <Pressable key={file.path} onPress={() => { void openFile(file.path); }} accessibilityRole="button" style={[styles.fileRow, selectedFile === file.path && styles.selectedRow]}>
            <Text style={styles.fileName}>{file.path}</Text><Text style={styles.fileMeta}>{file.size_bytes} B · r{file.revision}</Text>
          </Pressable>
        ))}
        {selectedFile ? <View style={styles.editor}>
          <View style={styles.sectionHeader}><Text style={styles.fileName}>{selectedFile}</Text><Text style={styles.fileMeta}>{t(language, 'revision')}: {fileRevision ?? '—'}</Text></View>
          <TextInput value={fileContent} onChangeText={setFileContent} multiline textAlignVertical="top" autoCapitalize="none" autoCorrect={false} spellCheck={false} style={styles.codeInput} accessibilityLabel={t(language, 'fileEditor')} />
          <View style={styles.inline}>
            <Pressable onPress={() => { void saveFile(); }} disabled={busy || fileRevision === null} accessibilityRole="button" style={[styles.button, (busy || fileRevision === null) && styles.disabled]}><Text style={styles.buttonText}>{t(language, 'saveFile')}</Text></Pressable>
            <Pressable onPress={deleteFile} disabled={busy} accessibilityRole="button" style={[styles.dangerButton, busy && styles.disabled]}><Text style={styles.dangerText}>{t(language, 'delete')}</Text></Pressable>
          </View>
        </View> : null}
        <View style={styles.checkpointSection}>
          <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>{t(language, 'checkpoints')}</Text><Pressable onPress={() => { void saveCheckpoint(); }} disabled={busy} accessibilityRole="button" style={[styles.button, busy && styles.disabled]}><Text style={styles.buttonText}>{t(language, 'createCheckpoint')}</Text></Pressable></View>
          {checkpoints.map((checkpoint) => <View key={checkpoint.id} style={styles.checkpointRow}>
            <Text style={styles.fileName}>{checkpoint.label}</Text>
            <Pressable onPress={() => { void showCheckpointDiff(checkpoint); }} disabled={busy} accessibilityRole="button" style={styles.linkButton}><Text style={styles.linkText}>{t(language, 'viewDiff')}</Text></Pressable>
          </View>)}
          {diff ? <View style={styles.diffBox}>
            <Text style={styles.sectionTitle}>{t(language, 'checkpointDiff')}</Text>
            {diff.changes.length === 0 ? <Text style={styles.muted}>{t(language, 'noDiff')}</Text> : diff.changes.map((change) => <View key={change.path} style={styles.diffItem}>
              <Text style={styles.fileName}>{change.change.toUpperCase()} · {change.path}</Text>
              <Text selectable style={styles.diffText}>{change.diff}</Text>
            </View>)}
          </View> : null}
        </View>
      </View> : null}
      {busy ? <View style={styles.inline}><ActivityIndicator color={palette.accent} /><Text style={styles.muted}>{t(language, 'loading')}</Text></View> : null}
    </ScrollView>
  );
}

function makeStyles(c: Palette, rtl: boolean) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bg },
    content: { padding: 18, gap: 14, maxWidth: 920, width: '100%', alignSelf: 'center' },
    fill: { flex: 1 },
    title: { color: c.text, fontSize: 26, fontWeight: '800', textAlign: rtl ? 'right' : 'left' },
    body: { color: c.muted, fontSize: 14, lineHeight: 21, textAlign: rtl ? 'right' : 'left' },
    card: { backgroundColor: c.panel, borderColor: c.border, borderWidth: 1, borderRadius: 16, padding: 14, gap: 10 },
    sectionTitle: { color: c.text, fontSize: 16, fontWeight: '700', textAlign: rtl ? 'right' : 'left' },
    sectionHeader: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
    inline: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 8 },
    input: { flex: 1, minWidth: 80, color: c.text, backgroundColor: c.bg, borderColor: c.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, textAlign: rtl ? 'right' : 'left' },
    button: { backgroundColor: c.accent, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, alignItems: 'center', justifyContent: 'center' },
    disabled: { opacity: 0.5 },
    buttonText: { color: '#fff', fontSize: 13, fontWeight: '700' },
    projectRow: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', gap: 10, borderBottomColor: c.border, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 10 },
    selectedRow: { backgroundColor: c.panel2, borderRadius: 8, paddingHorizontal: 8 },
    projectName: { color: c.text, fontSize: 15, fontWeight: '700', textAlign: rtl ? 'right' : 'left' },
    muted: { color: c.muted, fontSize: 12, lineHeight: 18, textAlign: rtl ? 'right' : 'left' },
    fileRow: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingVertical: 9, paddingHorizontal: 8, borderBottomColor: c.border, borderBottomWidth: StyleSheet.hairlineWidth },
    fileName: { color: c.text, fontSize: 13, fontWeight: '600', flexShrink: 1 },
    fileMeta: { color: c.muted, fontSize: 11 },
    editor: { gap: 10, borderTopColor: c.border, borderTopWidth: 1, paddingTop: 12, marginTop: 8 },
    codeInput: { minHeight: 220, maxHeight: 560, color: c.text, backgroundColor: c.bg, borderColor: c.border, borderWidth: 1, borderRadius: 10, padding: 12, fontFamily: 'monospace', fontSize: 12, lineHeight: 18, textAlign: 'left' },
    dangerButton: { paddingHorizontal: 12, paddingVertical: 9, borderWidth: 1, borderColor: c.danger, borderRadius: 10, alignItems: 'center' },
    dangerText: { color: c.danger, fontWeight: '700', fontSize: 12 },
    checkpointSection: { gap: 8, borderTopColor: c.border, borderTopWidth: 1, paddingTop: 12, marginTop: 8 },
    checkpointRow: { flexDirection: rtl ? 'row-reverse' : 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8 },
    linkButton: { padding: 6 },
    linkText: { color: c.accent, fontSize: 12, fontWeight: '700' },
    diffBox: { padding: 10, backgroundColor: c.bg, borderColor: c.border, borderWidth: 1, borderRadius: 10, gap: 8 },
    diffItem: { gap: 5 },
    diffText: { color: c.muted, fontFamily: 'monospace', fontSize: 11, lineHeight: 16 },
    error: { color: c.danger, backgroundColor: c.panel, borderRadius: 8, padding: 10 },
    notice: { color: c.accent, fontWeight: '700' },
  });
}
