// Types mirroring the FastAPI /mix/analyze response shape

export interface BandProfile {
  sub: number
  low: number
  low_mid: number
  mid: number
  high_mid: number
  high: number
  air: number
}

export interface SpectralData {
  bands: BandProfile
  spectral_centroid_hz: number
  spectral_tilt_db_oct: number
  spectral_flatness?: number
  overall_rms_db?: number
}

export interface StereoData {
  width: number
  lr_correlation: number
  mid_side_ratio_db?: number
  band_widths?: Partial<BandProfile>
}

export interface DynamicsData {
  lufs: number
  rms_db?: number
  peak_db: number
  crest_factor_db?: number
  dynamic_range_db?: number
  loudness_range_lu?: number
}

export interface TransientsData {
  onset_density_per_sec?: number
  attack_sharpness?: number
  attack_ratio?: number
}

export interface RecommendationStep {
  action: string
  bus: string
  plugin_primary?: string
  params?: Array<{ name: string; value: string | number }>
}

export interface Recommendation {
  problem_category: string
  severity: number
  summary: string
  steps?: RecommendationStep[]
  rag_query?: string
  citations?: number[]
}

export interface MixProblem {
  category: string
  severity: number
  frequency_range_hz?: [number, number]
  description: string
  recommendation: string
}

export interface MixReport {
  spectral: SpectralData
  stereo: StereoData | null
  dynamics: DynamicsData
  transients?: TransientsData
  problems: MixProblem[]
  recommendations: Recommendation[]
  genre: string
  duration_sec?: number
  sample_rate?: number
}

// Genre target band profiles (dBFS targets)
export const GENRE_TARGETS: Record<string, BandProfile> = {
  'organic house': {
    sub: -6.0, low: -4.0, low_mid: -8.0,
    mid: -10.0, high_mid: -12.0, high: -16.0, air: -22.0,
  },
  'melodic techno': {
    sub: -7.0, low: -5.0, low_mid: -9.0,
    mid: -11.0, high_mid: -13.0, high: -17.0, air: -23.0,
  },
  'deep house': {
    sub: -5.0, low: -3.0, low_mid: -8.0,
    mid: -11.0, high_mid: -13.0, high: -17.0, air: -24.0,
  },
  'progressive house': {
    sub: -7.0, low: -5.0, low_mid: -8.0,
    mid: -10.0, high_mid: -11.0, high: -15.0, air: -21.0,
  },
  'afro house': {
    sub: -6.0, low: -3.0, low_mid: -7.0,
    mid: -10.0, high_mid: -12.0, high: -16.0, air: -22.0,
  },
}

export const SUPPORTED_GENRES = Object.keys(GENRE_TARGETS)

export const BAND_LABELS: Record<keyof BandProfile, { short: string; range: string }> = {
  sub:      { short: 'SUB',  range: '20-60Hz' },
  low:      { short: 'LOW',  range: '60-200Hz' },
  low_mid:  { short: 'LMD',  range: '200-500Hz' },
  mid:      { short: 'MID',  range: '500-2kHz' },
  high_mid: { short: 'HMD',  range: '2-6kHz' },
  high:     { short: 'HGH',  range: '6-12kHz' },
  air:      { short: 'AIR',  range: '12-20kHz' },
}
