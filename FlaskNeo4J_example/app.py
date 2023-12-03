from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os #provides ways to access the Operating System and allows us to read the environment variables

load_dotenv()

app = Flask(__name__)

uri = os.getenv('URI')
user = os.getenv("USERNAME1")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password),database="neo4j")

# Query do stworzenia initial bazy danych
# CREATE (john:Employee {first_name: 'John', last_name: 'Doe', position: 'Manager'})
# CREATE (alice:Employee {first_name: 'Alice', last_name: 'Smith', position: 'Developer'})
# CREATE (bob:Employee {first_name: 'Bob', last_name: 'Johnson', position: 'Analyst'})
# CREATE (it:Department {name: 'IT'})
# CREATE (hr:Department {name: 'HR'})
# CREATE (john)-[:WORKS_IN]->(it)
# CREATE (alice)-[:WORKS_IN]->(it)
# CREATE (bob)-[:WORKS_IN]->(hr)
# CREATE (john)-[:MANAGES]->(it)


def get_employees(tx, filter_first_name=None, filter_last_name=None, filter_position=None, sort_by=None):
    query = "MATCH (m:Employee) "

    filters = []
    if filter_first_name:
        filters.append(f"toLower(m.first_name) CONTAINS toLower('{filter_first_name}')")
    if filter_last_name:
        filters.append(f"toLower(m.last_name) CONTAINS toLower('{filter_last_name}')")
    if filter_position:
        filters.append(f"toLower(m.position) CONTAINS toLower('{filter_position}')")

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += "RETURN ID(m), m"

    if sort_by:
        query += f" ORDER BY m.{sort_by}"

    results = tx.run(query).data()
    employees = [{'id': result['ID(m)'],'first_name': result['m']['first_name'], 'last_name': result['m']['last_name'], 'position': result['m']['position']} for result in results]
    return employees

@app.route('/employees', methods=['GET'])
def get_employees_route():
    filter_first_name = request.args.get('filter_first_name')
    filter_last_name = request.args.get('filter_last_name')
    filter_position = request.args.get('filter_position')
    sort_by = request.args.get('sort_by')

    with driver.session() as session:
        employees = session.read_transaction(get_employees,filter_first_name=filter_first_name, filter_last_name=filter_last_name, filter_position=filter_position, sort_by=sort_by)

    response = {'emp': employees}
    return jsonify(response)

def add_employee(tx, first_name, last_name, position, department_id):
    check_query = "MATCH (employee:Employee) WHERE employee.first_name = $first_name AND employee.last_name = $last_name RETURN COUNT(employee) as count"
    existing_count = tx.run(check_query, first_name=first_name, last_name=last_name).single()['count']

    if existing_count > 0:
        return None

    if not first_name or not last_name or not position or not department_id:
        return None


    query = (
        "CREATE (employee:Employee {first_name: $first_name, last_name: $last_name, position: $position}) "
        "WITH employee "
        "MATCH (department:Department) WHERE department.id = $department_id "
        "CREATE (employee)-[:WORKS_IN]->(department)"
    )
    tx.run(query, first_name=first_name, last_name=last_name, position=position, department_id=department_id)

@app.route('/employees', methods=['POST'])
def add_emplyee_route():
    first_name = request.json['first_name']
    last_name = request.json['last_name']
    position = request.json['position']
    department_id = request.json['department_id']

    with driver.session() as session:
        session.write_transaction(add_employee,first_name, last_name, position, department_id)

    respone = {'status': 'success'}
    return jsonify(respone)


def update_employee(tx, id, new_name, new_last_name, new_position):
    query = "MATCH (m:Employee) WHERE m.id=$id RETURN m"
    result = tx.run(query, id=id).data()

    if not result:
        return None
    else:
        query = "MATCH (m:Employee) WHERE m.id=$id SET m.first_name=$new_name, m.last_name=$new_last_name, m.position=$new_position"
        tx.run(query, id=id, new_name=new_name, new_last_name=new_last_name, new_position=new_position)
        return {'first_name': new_name, 'last_name': new_last_name, 'position': new_position}

@app.route('/employees/<int:id>', methods=['PUT'])
def update_employee_route(id):
    new_name = request.json['first_name']
    new_last_name = request.json['last_name']
    new_position = request.json['position']

    with driver.session() as session:
        employee = session.write_transaction(update_employee, id, new_name, new_last_name, new_position)

    if not employee:
        response = {'message': 'Employee not found'}
        return jsonify(response), 404
    else:
        response = {'status': 'success'}
        return jsonify(response)

#DODAC JESZCE UPDATE DLA DEPARTMENT

def delete_employee(tx, employee_id):
    # Find the employee and associated department
    query = (
        "MATCH (employee:Employee) WHERE ID(employee)=$employee_id "
        "OPTIONAL MATCH (employee)-[:MANAGES]->(department:Department) "
        "RETURN employee, department"
    )
    result = tx.run(query, employee_id=employee_id).single()

    if not result:
        return None
    else:
        employee = result['employee']
        department = result['department']

        # Delete the employee and the management relationship
        tx.run("MATCH (e:Employee) WHERE ID(e)=$employee_id DETACH DELETE e", employee_id=employee_id)

        if department:
            # Check if there are other managers in the department
            manager_count_query = (
                "MATCH (d:Department)<-[:MANAGES]-(m:Employee) "
                "WHERE ID(d)=$department_id AND ID(m) <> $employee_id "
                "RETURN COUNT(m) as manager_count"
            )
            manager_count = tx.run(manager_count_query, department_id=department.id, employee_id=employee.id).single()['manager_count']

            if manager_count == 0:
                # No other manager, check if there are remaining employees in the department
                remaining_employees_query = (
                    "MATCH (d:Department)<-[:WORKS_IN]-(e:Employee) "
                    "WHERE ID(d)=$department_id "
                    "RETURN COUNT(e) as employee_count"
                )
                employee_count = tx.run(remaining_employees_query, department_id=department.id).single()['employee_count']

                if employee_count > 0:
                    # There are remaining employees, designate a new manager
                    new_manager_query = (
                        "MATCH (d:Department)<-[:WORKS_IN]-(e:Employee) "
                        "WHERE ID(d)=$department_id "
                        "WITH e LIMIT 1 "
                        "CREATE (e)-[:MANAGES]->(d)"
                    )
                    tx.run(new_manager_query, department_id=department.id)
                else:
                    tx.run("MATCH (d:Department) WHERE ID(d)=$department_id DETACH DELETE d", department_id=department.id)

# Flask route for handling the DELETE request
@app.route('/employees/<int:id>', methods=['DELETE'])
def delete_employee_route(id):
    with driver.session() as session:
        employee = session.write_transaction(delete_employee, employee_id=id)

    if not employee:
        response = {'message': 'Employee not found'}
        return jsonify(response), 404
    else:
        response = {'status': 'success'}
        return jsonify(response)


    
def subordinates(tx, id):
    query = "MATCH (manager:Employee)-[:MANAGES]->(:Department)<-[:WORKS_IN]-(employee:Employee) WHERE ID(manager)=$id AND ID(employee)<>$id RETURN employee"
    results = tx.run(query, id=id).data()
    response = [{'first_name': result['employee']['first_name'], 'last_name': result['employee']['last_name'], 'position': result['employee']['position']} for result in results]
    return response


    
@app.route('/employees/<int:id>/subordinates', methods=['GET'])
def get_subordinates_info_route(id):
    with driver.session() as session:
        info = session.read_transaction(subordinates, id=id)

    return jsonify(info)

def get_emp_dep_info(tx, id):
    query = "MATCH (employee:Employee)-[:WORKS_IN]->(department:Department)<-[:MANAGES]-(manger:Employee) WHERE ID(employee)=$id RETURN department.name as department_name, count(employee) as employee_count, manger.first_name as manger_first_name, manger.last_name as manger_last_name"
    result = tx.run(query, id=id).single()
    response = [{"dept_name": result['department_name'], "emp_count": result['employee_count']+1, "manger": {"first_name": result['manger_first_name'], "last_name": result['manger_last_name']}}]
    return response


@app.route('/employees/<int:id>/department', methods=['GET'])
def get_employee_department_info(id):
    with driver.session() as session:
        info = session.read_transaction(get_emp_dep_info, id=id)

    return jsonify(info)

def get_departments(tx, filter_name=None, sort_by=None):
    query = "MATCH (employee:Employee)-[:WORKS_IN]->(department:Department)"

    if filter_name:
        query += f" WHERE toLower(department.name) CONTAINS toLower('{filter_name}')"

    query += " RETURN department, count(employee) as count_of_emp"

    print(query)

    if sort_by == 'department':
        query += f" ORDER BY department.{sort_by}"
    elif sort_by == 'Emp_count':
        query += f" ORDER BY employee.{sort_by}"

    results = tx.run(query).data()
    response = [{"department": result['department']['name'], "Emp_count": result['count_of_emp']} for result in results]
    return response


@app.route('/departments', methods=['GET'])
def get_department_route():
    filter_name = request.args.get('filter_name')
    sort_by = request.args.get('sort_by')

    with driver.session() as session:
        info = session.read_transaction(get_departments, filter_name=filter_name, sort_by=sort_by)

    return jsonify(info)

def get_dept_emp(tx,id):
    query = "MATCH (employee:Employee)-[:WORKS_IN]->(department:Department) WHERE ID(department)=$id RETURN employee"
    results = tx.run(query, id=id).data()
    response = [{'first_name': result['employee']['first_name'], 'last_name': result['employee']['last_name'], 'position': result['employee']['position']} for result in results]
    return response

@app.route('/departments/<int:id>/employees', methods=['GET'])
def get_dept_emp_route(id):
    with driver.session() as session:
        info = session.read_transaction(get_dept_emp, id=id)

    return jsonify(info)

if __name__ == '__main__':
    app.run()
