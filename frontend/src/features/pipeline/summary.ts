import type { components } from '@/api/schema'

export type PipelineStatus = components['schemas']['PipelineStatusRead']
export type PipelineQueue = components['schemas']['QueueRead']

/** Minutes as "~45 min" or "~2 h 27 min". */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `~${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `~${hours} h` : `~${hours} h ${rest} min`
}

/** One line for the sidebar: what the pipeline is doing now, or what is wrong with it. */
export function headline(status: PipelineStatus): string {
  switch (status.state) {
    case 'no_ai':
      return 'Job analysis is off'
    case 'worker_stopped':
      return 'Worker not responding'
    case 'collecting':
      // The worker collects first and analyses afterwards, so the jobs wait on purpose.
      return 'Collecting…'
    case 'no_progress':
      return `No progress in the last ${status.recent.window_minutes} min`
    default:
      if (status.analysis.waiting > 0) {
        return `Analysing ${status.analysis.done} of ${status.analysis.total}`
      }
      if (status.scoring.waiting > 0) {
        return `Scoring ${status.scoring.done} of ${status.scoring.total}`
      }
      return 'Up to date'
  }
}

/** The pace of a stage and the time left, e.g. "3/min · ~2 h 27 min left"; empty when done. */
export function pace(queue: PipelineQueue, perMinute: number): string {
  if (queue.waiting === 0) return ''
  if (perMinute <= 0 || typeof queue.minutes_left !== 'number') return 'no recent progress'
  return `${perMinute}/min · ${formatMinutes(queue.minutes_left)} left`
}
