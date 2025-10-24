# Makefile for sample debugging program

CC = gcc
CFLAGS = -g -O0 -pthread -Wall
TARGET = sample_program

all: $(TARGET)

$(TARGET): sample_program.c
	$(CC) $(CFLAGS) -o $(TARGET) sample_program.c

clean:
	rm -f $(TARGET) core.* *.o

# Run the program
run: $(TARGET)
	./$(TARGET)

# Enable core dumps and run (useful for testing core dump analysis)
run-with-core: $(TARGET)
	ulimit -c unlimited && ./$(TARGET)

.PHONY: all clean run run-with-core
