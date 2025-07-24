//! Work-Stealing Parallelism Module
//!
//! This module implements a work-stealing scheduler for verification tasks to maximize
//! CPU utilization across multiple cores with dynamic load balancing.
//!
//! Note: This module is not available in WebAssembly builds due to threading limitations.

#![cfg(not(target_arch = "wasm32"))]

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};
#[cfg(feature = "crossbeam-channel")]
use crossbeam_channel::{unbounded, Receiver, Sender};
#[cfg(feature = "rayon")]
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use crate::{
    core::{VerificationResult, LemmaCore},
    credentials::VerifiableCredential,
    Result, LemmaError
};

/// Maximum number of worker threads
const MAX_WORKERS: usize = 64;
/// Default work queue size per worker
const DEFAULT_QUEUE_SIZE: usize = 1000;
/// Steal attempt threshold before sleeping
const STEAL_ATTEMPTS: usize = 5;
/// Sleep duration when no work is available
const IDLE_SLEEP_MS: u64 = 1;

/// Verification task for work-stealing queue
#[derive(Debug, Clone)]
pub struct VerificationTask {
    /// Task ID for tracking
    pub id: u64,
    /// Credential to verify
    pub credential: VerifiableCredential,
    /// Task priority (higher = more important)
    pub priority: u8,
    /// Submitted timestamp
    pub submitted_at: Instant,
    /// Result sender
    pub result_sender: Sender<TaskResult>,
}

/// Task result with metadata
#[derive(Debug)]
pub struct TaskResult {
    /// Task ID
    pub task_id: u64,
    /// Verification result
    pub result: Result<VerificationResult>,
    /// Processing time
    pub processing_time: Duration,
    /// Worker ID that processed this task
    pub worker_id: usize,
}

/// Work-stealing queue for a single worker
pub struct WorkStealingQueue {
    /// Task queue (deque for efficient push/pop)
    queue: Arc<Mutex<VecDeque<VerificationTask>>>,
    /// Queue capacity
    capacity: usize,
    /// Worker statistics
    stats: Arc<Mutex<WorkerStats>>,
}

/// Worker statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerStats {
    /// Tasks processed
    pub tasks_processed: u64,
    /// Tasks stolen from this worker
    pub tasks_stolen: u64,
    /// Tasks stolen by this worker
    pub tasks_stolen_by: u64,
    /// Total processing time
    pub total_processing_time: Duration,
    /// Idle time
    pub idle_time: Duration,
    /// Average task processing time
    pub avg_processing_time: Duration,
}

impl WorkStealingQueue {
    /// Create a new work-stealing queue
    pub fn new(capacity: usize) -> Self {
        Self {
            queue: Arc::new(Mutex::new(VecDeque::with_capacity(capacity))),
            capacity,
            stats: Arc::new(Mutex::new(WorkerStats {
                tasks_processed: 0,
                tasks_stolen: 0,
                tasks_stolen_by: 0,
                total_processing_time: Duration::ZERO,
                idle_time: Duration::ZERO,
                avg_processing_time: Duration::ZERO,
            })),
        }
    }

    /// Push a task to the queue (bottom)
    pub fn push(&self, task: VerificationTask) -> Result<()> {
        let mut queue = self.queue.lock().unwrap();
        if queue.len() >= self.capacity {
            return Err(LemmaError::VerificationFailed("Work queue full".to_string()));
        }
        queue.push_back(task);
        Ok(())
    }

    /// Pop a task from the queue (bottom - LIFO for locality)
    pub fn pop(&self) -> Option<VerificationTask> {
        let mut queue = self.queue.lock().unwrap();
        queue.pop_back()
    }

    /// Steal a task from the queue (top - FIFO for fairness)
    pub fn steal(&self) -> Option<VerificationTask> {
        let mut queue = self.queue.lock().unwrap();
        let task = queue.pop_front();
        if task.is_some() {
            let mut stats = self.stats.lock().unwrap();
            stats.tasks_stolen += 1;
        }
        task
    }

    /// Get queue length
    pub fn len(&self) -> usize {
        let queue = self.queue.lock().unwrap();
        queue.len()
    }

    /// Check if queue is empty
    pub fn is_empty(&self) -> bool {
        let queue = self.queue.lock().unwrap();
        queue.is_empty()
    }

    /// Get worker statistics
    pub fn get_stats(&self) -> WorkerStats {
        self.stats.lock().unwrap().clone()
    }

    /// Update statistics after task completion
    pub fn update_stats(&self, processing_time: Duration, stolen_by: bool) {
        let mut stats = self.stats.lock().unwrap();
        stats.tasks_processed += 1;
        stats.total_processing_time += processing_time;
        stats.avg_processing_time = stats.total_processing_time / stats.tasks_processed as u32;
        
        if stolen_by {
            stats.tasks_stolen_by += 1;
        }
    }

    /// Update idle time statistics
    pub fn update_idle_time(&self, idle_time: Duration) {
        let mut stats = self.stats.lock().unwrap();
        stats.idle_time += idle_time;
    }
}

/// Work-stealing scheduler configuration
#[derive(Debug, Clone)]
pub struct WorkStealingConfig {
    /// Number of worker threads
    pub num_workers: usize,
    /// Queue size per worker
    pub queue_size: usize,
    /// Enable priority scheduling
    pub priority_scheduling: bool,
    /// Steal attempts before sleeping
    pub steal_attempts: usize,
    /// Idle sleep duration
    pub idle_sleep_ms: u64,
}

impl Default for WorkStealingConfig {
    fn default() -> Self {
        Self {
            num_workers: num_cpus::get(),
            queue_size: DEFAULT_QUEUE_SIZE,
            priority_scheduling: true,
            steal_attempts: STEAL_ATTEMPTS,
            idle_sleep_ms: IDLE_SLEEP_MS,
        }
    }
}

/// Work-stealing scheduler statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkStealingStats {
    /// Total tasks processed
    pub total_tasks_processed: u64,
    /// Total tasks submitted
    pub total_tasks_submitted: u64,
    /// Tasks currently in queues
    pub tasks_in_queues: usize,
    /// Active workers
    pub active_workers: usize,
    /// Total workers
    pub total_workers: usize,
    /// Average task processing time
    pub avg_processing_time: Duration,
    /// Throughput (tasks/second)
    pub throughput: f64,
    /// CPU utilization
    pub cpu_utilization: f64,
    /// Work stealing efficiency
    pub stealing_efficiency: f64,
    /// Per-worker statistics
    pub worker_stats: Vec<WorkerStats>,
}

/// Work-stealing scheduler for verification tasks
pub struct WorkStealingScheduler {
    /// Configuration
    config: WorkStealingConfig,
    /// Work queues (one per worker)
    queues: Vec<Arc<WorkStealingQueue>>,
    /// Worker threads
    workers: Vec<std::thread::JoinHandle<()>>,
    /// Task ID counter
    next_task_id: AtomicUsize,
    /// Shutdown flag
    shutdown: Arc<AtomicBool>,
    /// Task submission channel
    task_sender: Sender<VerificationTask>,
    /// Result collection channel
    result_receiver: Receiver<TaskResult>,
    /// Scheduler statistics
    stats: Arc<Mutex<WorkStealingStats>>,
}

impl WorkStealingScheduler {
    /// Create a new work-stealing scheduler
    pub fn new(config: WorkStealingConfig) -> Result<Self> {
        let num_workers = config.num_workers.min(MAX_WORKERS);
        let mut queues = Vec::with_capacity(num_workers);
        
        // Create work queues
        for _ in 0..num_workers {
            queues.push(Arc::new(WorkStealingQueue::new(config.queue_size)));
        }

        // Create communication channels
        let (task_sender, task_receiver) = unbounded();
        let (result_sender, result_receiver) = unbounded();

        // Initialize statistics
        let stats = Arc::new(Mutex::new(WorkStealingStats {
            total_tasks_processed: 0,
            total_tasks_submitted: 0,
            tasks_in_queues: 0,
            active_workers: num_workers,
            total_workers: num_workers,
            avg_processing_time: Duration::ZERO,
            throughput: 0.0,
            cpu_utilization: 0.0,
            stealing_efficiency: 0.0,
            worker_stats: vec![WorkerStats {
                tasks_processed: 0,
                tasks_stolen: 0,
                tasks_stolen_by: 0,
                total_processing_time: Duration::ZERO,
                idle_time: Duration::ZERO,
                avg_processing_time: Duration::ZERO,
            }; num_workers],
        }));

        // Create workers
        let mut workers = Vec::with_capacity(num_workers);
        let shutdown = Arc::new(AtomicBool::new(false));
        
        for worker_id in 0..num_workers {
            let queue = queues[worker_id].clone();
            let all_queues = queues.clone();
            let task_receiver = task_receiver.clone();
            let result_sender = result_sender.clone();
            let config = config.clone();
            let shutdown = shutdown.clone();
            let stats = stats.clone();

            let worker = std::thread::Builder::new()
                .name(format!("lemma-worker-{}", worker_id))
                .spawn(move || {
                    Self::worker_loop(
                        worker_id,
                        queue,
                        all_queues,
                        task_receiver,
                        result_sender,
                        config,
                        shutdown,
                        stats,
                    );
                })
                .map_err(|e| LemmaError::VerificationFailed(format!("Failed to create worker thread: {}", e)))?;

            workers.push(worker);
        }

        Ok(Self {
            config,
            queues,
            workers,
            next_task_id: AtomicUsize::new(1),
            shutdown,
            task_sender,
            result_receiver,
            stats,
        })
    }

    /// Worker thread main loop
    fn worker_loop(
        worker_id: usize,
        own_queue: Arc<WorkStealingQueue>,
        all_queues: Vec<Arc<WorkStealingQueue>>,
        task_receiver: Receiver<VerificationTask>,
        result_sender: Sender<TaskResult>,
        config: WorkStealingConfig,
        shutdown: Arc<AtomicBool>,
        _stats: Arc<Mutex<WorkStealingStats>>,
    ) {
        let mut core = LemmaCore::new().expect("Failed to create LemmaCore");
        
        // Register packages
        core.register_package(crate::packages::IdentityPackage::new());
        core.register_package(crate::packages::TicketPackage::new());
        core.register_package(crate::packages::PackageAuthenticityPackage::new());

        while !shutdown.load(Ordering::Relaxed) {
            let mut task_found = false;
            let idle_start = Instant::now();

            // 1. Try to get a task from global queue first
            if let Ok(task) = task_receiver.try_recv() {
                if let Err(_) = own_queue.push(task) {
                    // Queue is full, try other queues
                    for (i, queue) in all_queues.iter().enumerate() {
                        if i != worker_id && queue.len() < config.queue_size {
                            if let Ok(task) = task_receiver.try_recv() {
                                if let Ok(()) = queue.push(task) {
                                    break;
                                }
                            }
                        }
                    }
                }
            }

            // 2. Try to get a task from own queue
            if let Some(task) = own_queue.pop() {
                task_found = true;
                let processing_start = Instant::now();
                
                // Process the task
                let result = core.verify(&task.credential);
                let processing_time = processing_start.elapsed();

                // Send result
                let task_result = TaskResult {
                    task_id: task.id,
                    result,
                    processing_time,
                    worker_id,
                };

                if let Err(_) = result_sender.send(task_result) {
                    // Result channel closed, probably shutting down
                    break;
                }

                // Update statistics
                own_queue.update_stats(processing_time, false);
            }

            // 3. If no task found, try to steal from other workers
            if !task_found {
                let mut steal_attempts = 0;
                
                while steal_attempts < config.steal_attempts && !shutdown.load(Ordering::Relaxed) {
                    // Try to steal from a random worker
                    let target_worker = fastrand::usize(0..all_queues.len());
                    if target_worker != worker_id {
                        if let Some(task) = all_queues[target_worker].steal() {
                            task_found = true;
                            let processing_start = Instant::now();
                            
                            // Process the stolen task
                            let result = core.verify(&task.credential);
                            let processing_time = processing_start.elapsed();

                            // Send result
                            let task_result = TaskResult {
                                task_id: task.id,
                                result,
                                processing_time,
                                worker_id,
                            };

                            if let Err(_) = result_sender.send(task_result) {
                                break;
                            }

                            // Update statistics (task was stolen)
                            own_queue.update_stats(processing_time, true);
                            break;
                        }
                    }
                    steal_attempts += 1;
                }
            }

            // 4. If still no task, sleep briefly
            if !task_found {
                let idle_time = idle_start.elapsed();
                own_queue.update_idle_time(idle_time);
                
                std::thread::sleep(Duration::from_millis(config.idle_sleep_ms));
            }
        }
    }

    /// Submit a verification task
    pub fn submit_task(&self, credential: VerifiableCredential, priority: u8) -> Result<u64> {
        let task_id = self.next_task_id.fetch_add(1, Ordering::SeqCst) as u64;
        
        let (result_sender, _) = unbounded();
        let task = VerificationTask {
            id: task_id,
            credential,
            priority,
            submitted_at: Instant::now(),
            result_sender,
        };

        self.task_sender.send(task)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to submit task: {}", e)))?;

        // Update statistics
        {
            let mut stats = self.stats.lock().unwrap();
            stats.total_tasks_submitted += 1;
        }

        Ok(task_id)
    }

    /// Submit multiple verification tasks
    pub fn submit_batch(&self, credentials: Vec<VerifiableCredential>, priority: u8) -> Result<Vec<u64>> {
        let mut task_ids = Vec::with_capacity(credentials.len());
        
        for credential in credentials {
            let task_id = self.submit_task(credential, priority)?;
            task_ids.push(task_id);
        }

        Ok(task_ids)
    }

    /// Get task results (non-blocking)
    pub fn get_results(&self) -> Vec<TaskResult> {
        let mut results = Vec::new();
        
        while let Ok(result) = self.result_receiver.try_recv() {
            results.push(result);
        }

        // Update statistics
        {
            let mut stats = self.stats.lock().unwrap();
            stats.total_tasks_processed += results.len() as u64;
        }

        results
    }

    /// Wait for specific task result
    pub fn wait_for_result(&self, task_id: u64, timeout: Duration) -> Result<TaskResult> {
        let start = Instant::now();
        
        while start.elapsed() < timeout {
            if let Ok(result) = self.result_receiver.try_recv() {
                if result.task_id == task_id {
                    return Ok(result);
                }
            }
            
            std::thread::sleep(Duration::from_millis(1));
        }

        Err(LemmaError::VerificationFailed("Task timeout".to_string()))
    }

    /// Get current statistics
    pub fn get_stats(&self) -> WorkStealingStats {
        let mut stats = self.stats.lock().unwrap();
        
        // Update queue statistics
        stats.tasks_in_queues = self.queues.iter().map(|q| q.len()).sum();
        
        // Update worker statistics
        stats.worker_stats.clear();
        for queue in &self.queues {
            stats.worker_stats.push(queue.get_stats());
        }

        // Calculate throughput
        let total_time: Duration = stats.worker_stats.iter()
            .map(|s| s.total_processing_time)
            .sum();
        
        if total_time > Duration::ZERO {
            stats.throughput = stats.total_tasks_processed as f64 / total_time.as_secs_f64();
        }

        // Calculate CPU utilization
        let total_idle: Duration = stats.worker_stats.iter()
            .map(|s| s.idle_time)
            .sum();
        
        let total_active = total_time + total_idle;
        if total_active > Duration::ZERO {
            stats.cpu_utilization = (total_time.as_secs_f64() / total_active.as_secs_f64()) * 100.0;
        }

        // Calculate stealing efficiency
        let total_stolen: u64 = stats.worker_stats.iter()
            .map(|s| s.tasks_stolen_by)
            .sum();
        
        if stats.total_tasks_processed > 0 {
            stats.stealing_efficiency = (total_stolen as f64 / stats.total_tasks_processed as f64) * 100.0;
        }

        stats.clone()
    }

    /// Shutdown the scheduler
    pub fn shutdown(&mut self) -> Result<()> {
        self.shutdown.store(true, Ordering::SeqCst);
        
        // Wait for all workers to finish
        while let Some(worker) = self.workers.pop() {
            worker.join().map_err(|e| {
                LemmaError::VerificationFailed(format!("Worker thread join failed: {:?}", e))
            })?;
        }

        Ok(())
    }
}

impl Drop for WorkStealingScheduler {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::credentials::CredentialIssuer;
    use std::collections::HashMap;

    #[test]
    fn test_work_stealing_queue() {
        let queue = WorkStealingQueue::new(100);
        assert!(queue.is_empty());
        assert_eq!(queue.len(), 0);

        let (sender, _) = unbounded();
        let task = VerificationTask {
            id: 1,
            credential: create_test_credential(),
            priority: 1,
            submitted_at: Instant::now(),
            result_sender: sender,
        };

        queue.push(task.clone()).unwrap();
        assert_eq!(queue.len(), 1);
        assert!(!queue.is_empty());

        let popped = queue.pop().unwrap();
        assert_eq!(popped.id, 1);
        assert!(queue.is_empty());
    }

    #[test]
    fn test_work_stealing_scheduler() {
        let config = WorkStealingConfig {
            num_workers: 2,
            queue_size: 10,
            priority_scheduling: true,
            steal_attempts: 5,
            idle_sleep_ms: 1,
        };

        let scheduler = WorkStealingScheduler::new(config).unwrap();
        
        // Submit some tasks
        let credential = create_test_credential();
        let task_id = scheduler.submit_task(credential, 1).unwrap();
        assert!(task_id > 0);

        // Give some time for processing
        std::thread::sleep(Duration::from_millis(100));

        // Check results
        let results = scheduler.get_results();
        assert!(!results.is_empty());
    }

    #[test]
    fn test_batch_submission() {
        let config = WorkStealingConfig {
            num_workers: 4,
            queue_size: 100,
            priority_scheduling: true,
            steal_attempts: 5,
            idle_sleep_ms: 1,
        };

        let scheduler = WorkStealingScheduler::new(config).unwrap();
        
        // Submit batch of tasks
        let credentials = vec![
            create_test_credential(),
            create_test_credential(),
            create_test_credential(),
        ];
        
        let task_ids = scheduler.submit_batch(credentials, 1).unwrap();
        assert_eq!(task_ids.len(), 3);

        // Give some time for processing
        std::thread::sleep(Duration::from_millis(200));

        // Check results
        let results = scheduler.get_results();
        assert!(results.len() >= 3);
    }

    fn create_test_credential() -> VerifiableCredential {
        let issuer = CredentialIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        ).unwrap()
    }
} 