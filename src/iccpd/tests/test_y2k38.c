/*
 * Y2K38 Test Suite for iccpd
 *
 * This test suite verifies that the time_t type used in iccpd is properly
 * sized to handle dates beyond January 19, 2038 (Y2K38 problem).
 *
 * The Y2K38 problem occurs when 32-bit signed integers used to store
 * Unix timestamps overflow on January 19, 2038 at 03:14:07 UTC.
 *
 * Copyright(c) 2024 Broadcom.
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms and conditions of the GNU General Public License,
 * version 2, as published by the Free Software Foundation.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <assert.h>

/* Include the Y2K38 time safety header */
#include "../include/iccp_time.h"

/* Y2K38 boundary timestamp: 2038-01-19 03:14:07 UTC */
#define Y2K38_BOUNDARY 2147483647LL

/* Test timestamps beyond Y2K38 */
#define YEAR_2040 2208988800LL  /* 2040-01-01 00:00:00 UTC */
#define YEAR_2050 2524608000LL  /* 2050-01-01 00:00:00 UTC */
#define YEAR_2100 4102444800LL  /* 2100-01-01 00:00:00 UTC */

static int tests_run = 0;
static int tests_passed = 0;

#define TEST_ASSERT(condition, message) do { \
    tests_run++; \
    if (condition) { \
        tests_passed++; \
        printf("PASS: %s\n", message); \
    } else { \
        printf("FAIL: %s\n", message); \
    } \
} while(0)

/*
 * Test 1: Verify time_t is at least 64-bit
 * This is the critical compile-time check from iccp_time.h
 */
void test_time_t_size(void)
{
    printf("\n=== Test 1: time_t size ===\n");

    /* time_t should be at least 8 bytes (64-bit) */
    TEST_ASSERT(sizeof(time_t) >= 8,
                "time_t should be at least 64-bit (8 bytes)");

    printf("sizeof(time_t) = %zu bytes\n", sizeof(time_t));
}

/*
 * Test 2: Verify time_t can store Y2K38 boundary value
 */
void test_time_t_y2k38_boundary(void)
{
    time_t t;

    printf("\n=== Test 2: time_t Y2K38 boundary ===\n");

    t = Y2K38_BOUNDARY;
    TEST_ASSERT(t == 2147483647LL,
                "time_t can store Y2K38 boundary value");

    /* Test one second past Y2K38 boundary */
    t = Y2K38_BOUNDARY + 1;
    TEST_ASSERT(t == 2147483648LL,
                "time_t can store value past Y2K38 boundary");
}

/*
 * Test 3: Verify time_t can store timestamps beyond 2038
 */
void test_time_t_future_timestamps(void)
{
    time_t t;

    printf("\n=== Test 3: time_t future timestamps ===\n");

    /* Test year 2040 */
    t = YEAR_2040;
    TEST_ASSERT(t == 2208988800LL,
                "time_t can store year 2040 timestamp");

    /* Test year 2050 */
    t = YEAR_2050;
    TEST_ASSERT(t == 2524608000LL,
                "time_t can store year 2050 timestamp");

    /* Test year 2100 */
    t = YEAR_2100;
    TEST_ASSERT(t == 4102444800LL,
                "time_t can store year 2100 timestamp");
}

/*
 * Test 4: Verify time_t arithmetic works correctly
 */
void test_time_t_arithmetic(void)
{
    time_t t1, t2, diff, sum;

    printf("\n=== Test 4: time_t arithmetic ===\n");

    /* Test subtraction across Y2K38 boundary */
    t1 = Y2K38_BOUNDARY + 1000000;
    t2 = Y2K38_BOUNDARY - 1000000;
    diff = t1 - t2;
    TEST_ASSERT(diff == 2000000,
                "Subtraction across Y2K38 boundary works correctly");

    /* Test addition beyond 32-bit max */
    t1 = Y2K38_BOUNDARY;
    sum = t1 + 1000000000LL;
    TEST_ASSERT(sum == 3147483647LL,
                "Addition beyond 32-bit max works correctly");

    /* Test large timestamp differences */
    t1 = YEAR_2100;
    t2 = YEAR_2040;
    diff = t1 - t2;
    TEST_ASSERT(diff == (YEAR_2100 - YEAR_2040),
                "Large timestamp differences calculated correctly");
}

/*
 * Test 5: Verify time_t comparison works correctly
 */
void test_time_t_comparison(void)
{
    time_t t1, t2;

    printf("\n=== Test 5: time_t comparison ===\n");

    t1 = Y2K38_BOUNDARY;
    t2 = Y2K38_BOUNDARY + 1;
    TEST_ASSERT(t1 < t2,
                "time_t comparison works at Y2K38 boundary");

    t1 = YEAR_2040;
    t2 = YEAR_2050;
    TEST_ASSERT(t1 < t2,
                "time_t comparison works for future timestamps");

    t1 = YEAR_2100;
    t2 = Y2K38_BOUNDARY;
    TEST_ASSERT(t1 > t2,
                "time_t comparison: 2100 > 2038");
}

/*
 * Test 6: Verify iccp_time_is_y2k38_safe function
 */
void test_iccp_time_is_y2k38_safe(void)
{
    int result;

    printf("\n=== Test 6: iccp_time_is_y2k38_safe ===\n");

    /* Current time should be before 2038, so this should return 1 */
    result = iccp_time_is_y2k38_safe();
    TEST_ASSERT(result == 1,
                "iccp_time_is_y2k38_safe returns 1 for current time");
}

/*
 * Test 7: Verify iccp_time_get_safe function
 */
void test_iccp_time_get_safe(void)
{
    time_t t;

    printf("\n=== Test 7: iccp_time_get_safe ===\n");

    t = iccp_time_get_safe();
    TEST_ASSERT(t > 0,
                "iccp_time_get_safe returns positive value");

    /* Verify the returned time is reasonable (after year 2020) */
    TEST_ASSERT(t > 1577836800LL,
                "iccp_time_get_safe returns time after 2020");
}

/*
 * Test 8: Verify Y2K38 boundary constants
 */
void test_y2k38_constants(void)
{
    printf("\n=== Test 8: Y2K38 constants ===\n");

    TEST_ASSERT(Y2K38_BOUNDARY_TIMESTAMP == 2147483647LL,
                "Y2K38_BOUNDARY_TIMESTAMP is correct");

    TEST_ASSERT(Y2K38_WARNING_THRESHOLD == 2145916800LL,
                "Y2K38_WARNING_THRESHOLD is correct (2038-01-01)");

    TEST_ASSERT(Y2K38_WARNING_THRESHOLD < Y2K38_BOUNDARY_TIMESTAMP,
                "Warning threshold is before boundary");
}

/*
 * Test 9: Simulate CSM heartbeat timestamps beyond 2038
 */
void test_csm_heartbeat_timestamps(void)
{
    time_t heartbeat_send_time;
    time_t heartbeat_update_time;
    time_t diff;

    printf("\n=== Test 9: CSM heartbeat timestamps ===\n");

    /* Simulate heartbeat times in year 2040 */
    heartbeat_send_time = YEAR_2040;
    heartbeat_update_time = YEAR_2040 + 5;  /* 5 seconds later */

    diff = heartbeat_update_time - heartbeat_send_time;
    TEST_ASSERT(diff == 5,
                "Heartbeat time difference calculated correctly in 2040");

    /* Simulate heartbeat times in year 2100 */
    heartbeat_send_time = YEAR_2100;
    heartbeat_update_time = YEAR_2100 + 10;  /* 10 seconds later */

    diff = heartbeat_update_time - heartbeat_send_time;
    TEST_ASSERT(diff == 10,
                "Heartbeat time difference calculated correctly in 2100");
}

/*
 * Test 10: Simulate warm reboot timestamps beyond 2038
 */
void test_warm_reboot_timestamps(void)
{
    time_t peer_warm_reboot_time;
    time_t warm_reboot_disconn_time;
    time_t current_time;
    time_t elapsed;

    printf("\n=== Test 10: Warm reboot timestamps ===\n");

    /* Simulate warm reboot in year 2040 */
    peer_warm_reboot_time = YEAR_2040;
    warm_reboot_disconn_time = YEAR_2040 + 30;  /* 30 seconds later */
    current_time = YEAR_2040 + 60;  /* 60 seconds after reboot */

    elapsed = current_time - peer_warm_reboot_time;
    TEST_ASSERT(elapsed == 60,
                "Warm reboot elapsed time calculated correctly in 2040");

    /* Verify disconnection time is between reboot and current */
    TEST_ASSERT(warm_reboot_disconn_time > peer_warm_reboot_time,
                "Disconnection time is after reboot time");
    TEST_ASSERT(warm_reboot_disconn_time < current_time,
                "Disconnection time is before current time");
}

int main(int argc, char *argv[])
{
    printf("========================================\n");
    printf("Y2K38 Test Suite for iccpd\n");
    printf("========================================\n");

    test_time_t_size();
    test_time_t_y2k38_boundary();
    test_time_t_future_timestamps();
    test_time_t_arithmetic();
    test_time_t_comparison();
    test_iccp_time_is_y2k38_safe();
    test_iccp_time_get_safe();
    test_y2k38_constants();
    test_csm_heartbeat_timestamps();
    test_warm_reboot_timestamps();

    printf("\n========================================\n");
    printf("Results: %d/%d tests passed\n", tests_passed, tests_run);
    printf("========================================\n");

    return (tests_passed == tests_run) ? 0 : 1;
}
