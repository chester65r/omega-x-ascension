import type { ExpoConfig } from 'expo/config';

const config: ExpoConfig = {
  name: 'Omega X Ascension',
  slug: 'omega-x-ascension',
  version: '0.1.0',
  orientation: 'portrait',
  userInterfaceStyle: 'automatic',
  platforms: ['android'],
  android: {
    package: 'com.omegaxascension.app',
    versionCode: 1,
    permissions: ['INTERNET'],
  },
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? '',
  },
};

export default config;
