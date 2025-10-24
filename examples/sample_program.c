/**
 * Sample C program for testing GDB MCP Server
 *
 * This program demonstrates various debugging scenarios:
 * - Multiple threads
 * - Mutex operations
 * - Potential deadlock
 * - Variable inspection
 */

#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>

pthread_mutex_t mutex1 = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t mutex2 = PTHREAD_MUTEX_INITIALIZER;

int counter = 0;
int array[10] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

typedef struct {
    int id;
    int iterations;
} thread_data_t;

void* worker_thread(void* arg) {
    thread_data_t* data = (thread_data_t*)arg;

    for (int i = 0; i < data->iterations; i++) {
        pthread_mutex_lock(&mutex1);
        counter++;

        // Simulate some work
        int local_value = counter;
        usleep(100);

        printf("Thread %d: counter = %d, local = %d\n", data->id, counter, local_value);

        pthread_mutex_unlock(&mutex1);
        usleep(1000);
    }

    return NULL;
}

void* mutex_user_thread(void* arg) {
    thread_data_t* data = (thread_data_t*)arg;

    // This thread acquires mutexes in order
    pthread_mutex_lock(&mutex1);
    printf("Thread %d: acquired mutex1\n", data->id);
    usleep(10000);

    pthread_mutex_lock(&mutex2);
    printf("Thread %d: acquired mutex2\n", data->id);

    // Do some work
    for (int i = 0; i < 5; i++) {
        array[i] *= 2;
    }

    pthread_mutex_unlock(&mutex2);
    pthread_mutex_unlock(&mutex1);

    return NULL;
}

int calculate_sum(int* arr, int size) {
    int sum = 0;
    for (int i = 0; i < size; i++) {
        sum += arr[i];
    }
    return sum;
}

int main(int argc, char* argv[]) {
    printf("Starting sample program...\n");

    const int num_threads = 4;
    pthread_t threads[num_threads];
    thread_data_t thread_data[num_threads];

    // Create worker threads
    for (int i = 0; i < num_threads - 1; i++) {
        thread_data[i].id = i + 1;
        thread_data[i].iterations = 5;
        pthread_create(&threads[i], NULL, worker_thread, &thread_data[i]);
    }

    // Create one mutex user thread
    thread_data[num_threads - 1].id = num_threads;
    thread_data[num_threads - 1].iterations = 1;
    pthread_create(&threads[num_threads - 1], NULL, mutex_user_thread, &thread_data[num_threads - 1]);

    // Main thread also does some work
    int sum = calculate_sum(array, 10);
    printf("Main thread: initial sum = %d\n", sum);

    // Wait for all threads
    for (int i = 0; i < num_threads; i++) {
        pthread_join(threads[i], NULL);
    }

    // Final calculations
    sum = calculate_sum(array, 10);
    printf("Final counter: %d\n", counter);
    printf("Final sum: %d\n", sum);

    printf("Program completed successfully\n");
    return 0;
}
