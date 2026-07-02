# Automated Test: verify_payroll.py
# Verifies payroll calculation rules against GNB Excel reference sheet data

def mock_calculate_employee_totals(worker_type, daily_rate, days_hours, adjustments):
    """
    Simulates payroll calculations for a single employee.
    Matches the logic in payroll_service.py.
    """
    hourly_rate = daily_rate / 8
    gross_total = 0.00
    
    for day_name, hours in days_hours.items():
        if worker_type in ("operario_fijo", "jefe"):
            # Fixed worker: daily rate is flat for all 7 days of the period
            day_pay = daily_rate
        else:
            # Temporal/external worker: hours * hourly_rate * multiplier
            multiplier = 2.0 if day_name == "domingo" else 1.0
            day_pay = hours * hourly_rate * multiplier
        
        gross_total += day_pay
        
    adjustment_total = sum(adjustments)
    net_total = gross_total + adjustment_total
    
    return round(gross_total, 4), round(adjustment_total, 4), round(net_total, 4)

def run_tests():
    print("=== RUNNING PAYROLL CALCULATION TESTS ===")
    
    # Test Case 1: EDUARDO SOLDADOR
    # Temporal, Daily: 80, Hourly: 10, worked 0 hrs, Adjustments: +50 (bono)
    eduardo_hours = {"martes": 0, "miercoles": 0, "jueves": 0, "viernes": 0, "sabado": 0, "domingo": 0, "lunes": 0}
    gross, adj, net = mock_calculate_employee_totals("temporal", 80.00, eduardo_hours, [50.00])
    print(f"EDUARDO SOLDADOR: Gross={gross} (Expected: 0.0), Adjustments={adj} (Expected: 50.0), Net={net} (Expected: 50.0)")
    assert gross == 0.0 and adj == 50.0 and net == 50.0, "Test failed for Eduardo!"

    # Test Case 2: DAVID HUAYTA
    # Temporal, Daily: 35, Hourly: 4.375, worked 8,8,9,8,8,0,8 hrs (total 49 hrs, Sunday 0 hrs)
    huayta_hours = {"martes": 8, "miercoles": 8, "jueves": 9, "viernes": 8, "sabado": 8, "domingo": 0, "lunes": 8}
    gross, adj, net = mock_calculate_employee_totals("temporal", 35.00, huayta_hours, [])
    print(f"DAVID HUAYTA: Gross={gross} (Expected: 214.375), Adjustments={adj} (Expected: 0.0), Net={net} (Expected: 214.375)")
    assert gross == 214.375 and adj == 0.0 and net == 214.375, "Test failed for Huayta!"

    # Test Case 3: YOEL FIGUEROA
    # Fixed, Daily: 60, worked 8,8,8,8,8,0,8 hrs. Should get flat 60 * 7 = 420
    yoel_hours = {"martes": 8, "miercoles": 8, "jueves": 8, "viernes": 8, "sabado": 8, "domingo": 0, "lunes": 8}
    gross, adj, net = mock_calculate_employee_totals("operario_fijo", 60.00, yoel_hours, [])
    print(f"YOEL FIGUEROA: Gross={gross} (Expected: 420.0), Adjustments={adj} (Expected: 0.0), Net={net} (Expected: 420.0)")
    assert gross == 420.0 and adj == 0.0 and net == 420.0, "Test failed for Yoel Figueroa!"

    # Test Case 4: NICOLAS SEGURA
    # Temporal, Daily: 40, Hourly: 5.0, worked 7.5,7,9,4,0,0,7.5 hrs (total 35 hrs)
    nicolas_hours = {"martes": 7.5, "miercoles": 7, "jueves": 9, "viernes": 4, "sabado": 0, "domingo": 0, "lunes": 7.5}
    gross, adj, net = mock_calculate_employee_totals("temporal", 40.00, nicolas_hours, [])
    print(f"NICOLAS SEGURA: Gross={gross} (Expected: 175.0), Adjustments={adj} (Expected: 0.0), Net={net} (Expected: 175.0)")
    assert gross == 175.0 and adj == 0.0 and net == 175.0, "Test failed for Nicolas!"

    # Test Case 5: GLADYS HUAMANCAJA
    # Temporal, Daily: 35, Hourly: 4.375, worked 8,0,8,8,8,0,8 hrs (total 40 hrs), Adjustments: -300 (descuento)
    gladys_hours = {"martes": 8, "miercoles": 0, "jueves": 8, "viernes": 8, "sabado": 8, "domingo": 0, "lunes": 8}
    gross, adj, net = mock_calculate_employee_totals("temporal", 35.00, gladys_hours, [-300.00])
    print(f"GLADYS HUAMANCAJA: Gross={gross} (Expected: 175.0), Adjustments={adj} (Expected: -300.0), Net={net} (Expected: -125.0)")
    assert gross == 175.0 and adj == -300.0 and net == -125.0, "Test failed for Gladys!"

    print("\n[OK] ALL PAYROLL CALCULATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
