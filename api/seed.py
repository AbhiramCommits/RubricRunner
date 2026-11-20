"""Seed RubricRunner with a realistic demo course.

Idempotent: re-running replaces the demo course (and everything under it) with
the same set of records, so repeated `make seed` calls converge on one state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import Assignment, Base, Course, RubricCriterion, Student, Submission

COURSE_NAME = "English 11 — Period 3"
ASSIGNMENT_TITLE = "Argumentative Essay: Should cities ban cars downtown?"
PROMPT_TEXT = (
    "Write a 250-400 word argumentative essay answering the question: Should cities ban "
    "private cars from their downtown cores? Take a clear position and defend it with "
    "specific evidence, examples, and reasoning. Address at least one counterargument."
)

RUBRIC = [
    (
        "Thesis",
        "Clear, arguable thesis statement that takes a position on the prompt and previews the "
        "reasons for that position.",
        5.0,
        0.2,
    ),
    (
        "Evidence",
        "Relevant evidence, examples, statistics, or cited sources that support each claim, with "
        "explanation of how the evidence proves the point.",
        10.0,
        0.4,
    ),
    (
        "Organization",
        "Logical structure: introduction, body paragraphs with transitions, a counterargument, "
        "and a conclusion that reinforces the thesis.",
        5.0,
        0.2,
    ),
    (
        "Mechanics",
        "Grammar, spelling, punctuation, and sentence clarity. Sentences are varied and readable.",
        5.0,
        0.2,
    ),
]

STUDENTS: list[tuple[str, str, str]] = [
    (
        "S01",
        "Priya Raman",
        """Cities built their downtowns for a world that no longer exists. Wide arterials designed to \
move commuters from suburb to office now sit half-empty for most of the day, while the sidewalks \
beside them bake in the sun. American cities should ban private cars from their downtown cores. \
The change would cut carbon emissions, make streets safer, and hand public space back to the \
people who actually live and shop there.

The environmental case is the strongest. Transportation is the largest source of United States \
carbon emissions, and passenger vehicles account for roughly 58 percent of that total, according \
to the Environmental Protection Agency. A downtown car ban would not eliminate driving, but it \
would remove the least efficient trips: short, congested journeys that burn fuel while producing \
almost no useful movement. When Oslo removed through-traffic from its center in 2019, the city \
recorded a measurable drop in local air pollution and a rise in pedestrian counts.

Safety follows the same logic. A pedestrian struck at 20 miles per hour has about a 90 percent \
chance of surviving; at 40 miles per hour that chance falls below 20 percent. Fewer cars means \
slower speeds, fewer blind corners, and fewer fatal collisions. Madrid's central car restrictions \
were associated with a double-digit decline in traffic deaths inside the cordon.

Skeptics argue that bans punish workers who cannot afford to live downtown and have no transit \
option. That objection is serious, but it is an argument for better buses and protected bike \
lanes, not for preserving a street design that fails everyone else. Cities can phase in \
restrictions, exempt delivery vehicles and accessible permits, and expand transit before the \
cordon begins.

Downtowns should be places for people, not parking lots with storefronts attached. A car ban is \
not a war on drivers; it is a decision about what a city is for. If leaders build the transit \
alternatives first and phase the policy honestly, the result will be cleaner air, safer streets, \
and a downtown that finally works for the people who use it.""",
    ),
    (
        "S02",
        "Marcus Chen",
        """Should cities ban cars from downtown? On balance, yes: a carefully designed ban would \
reduce emissions, free up valuable land, and make downtown streets safer. The policy is not \
costless, but the benefits clearly outweigh the costs.

Start with the air. According to the World Health Organization, road transport contributes \
roughly 15 percent of global carbon dioxide emissions and a much larger share of the nitrogen \
dioxide that concentrates on city blocks. Barcelona's superblock program, which closed selected \
streets to through traffic, was followed by a 25 percent reduction in traffic in those areas and \
measurable improvements in air quality. A downtown ban applies the same idea at a larger scale.

The economic argument is also stronger than critics admit. Parking consumes enormous amounts of \
land. In many American downtowns, surface parking covers more acreage than offices. Converting \
those lots into housing and shops raises the tax base and brings customers within walking \
distance of stores. When New York closed sections of Broadway to cars, nearby retail sales rose, \
according to a study by the city's transportation department.

Opponents reply that banning cars hurts small businesses that depend on customers arriving by \
car. Yet the evidence points the other way: pedestrian zones in Europe consistently report \
higher foot traffic and higher sales after the change. Delivery access can be preserved with \
time windows and loading zones, so the ban does not need to starve shops of goods.

The fairest objection is equity. A ban could burden people with disabilities or long commutes. \
That is why the policy should include accessible permits, frequent buses, and a phased timeline. \
A ban designed carelessly would be unfair; a ban designed well would expand opportunity for the \
majority of residents who do not drive downtown every day.

Cities should not treat streets as storage for private cars. A downtown car ban, paired with real \
transit investment, is a practical step toward cleaner air and a more livable city.""",
    ),
    (
        "S03",
        "Elena Rodriguez",
        """Downtown cores should become car-free. I support a ban on private vehicles in the central \
business district because it would reduce pollution, create safer streets, and make room for \
housing and small business.

Evidence from Europe is encouraging. According to a 2022 report from the Clean Cities Campaign, \
more than 300 European cities have established low-emission or car-free zones. In Ghent, the \
number of cyclists entering the center rose by 30 percent after restrictions began. These are \
not experiments in tiny tourist towns; they are working cities with commuters, deliveries, and \
weather.

Safety is another reason. Traffic crashes remain a leading cause of death for young people, and \
speed is the single biggest factor in whether a pedestrian survives. A study published in the \
Journal of Transport and Health found that lower speed limits and reduced car access cut serious \
injuries substantially. A ban goes further than a speed limit because it removes the vehicle, \
not just the acceleration.

Critics say that a ban will hurt downtown businesses. However, pedestrian streets often \
increase foot traffic. Customers on foot stop more often than drivers who are searching for a \
parking space, and shops in car-free zones report stable or rising revenue. Cities can also \
allow delivery vehicles in the early morning so that restaurants and stores still receive their \
supplies.

The main challenge is fairness. Some residents depend on cars because buses are unreliable. A \
responsible ban therefore needs frequent transit, safe bike routes, and exemptions for people \
with disabilities. Without those pieces, the policy would punish the wrong people.

Overall, the case for banning cars downtown is strong. Cleaner air, fewer deaths, and more \
usable public space are benefits that last. Cities should act, but they should act carefully and \
invest in alternatives at the same time.""",
    ),
    (
        "S04",
        "Jordan Blake",
        """Private cars should be banned from downtown areas. The reasons are simple: cars pollute, \
they kill people, and they take up space that cities could use far better.

First, consider pollution. According to the EPA, transportation produces about 29 percent of \
greenhouse gas emissions in the United States, and light-duty vehicles are the largest part of \
that. Downtown streets concentrate those emissions in the places where people walk and children \
play. Removing cars from a few square miles would improve air quality for thousands of \
residents and workers, especially those with asthma.

Second, cars make streets dangerous. A person hit by a car traveling 30 miles per hour is far \
more likely to die than a person hit at 15 miles per hour. Cities that have reduced car access, \
such as Madrid and Milan, have reported fewer serious crashes in their restricted zones. A ban \
would not stop every accident, but it would remove the most dangerous vehicles from the busiest \
blocks.

Third, parking wastes land. Downtown parking lots produce little tax revenue and create dead \
space between buildings. If even a fraction of those lots became apartments, the city would gain \
residents who support local shops and use public services more efficiently.

Some people argue that banning cars is unfair to drivers who live far away or who have \
disabilities. This is a real concern. Cities should keep accessible permits, allow delivery \
vehicles during set hours, and improve bus service before the ban starts. With those safeguards, \
the policy becomes fairer without losing its benefits.

A downtown without private cars is not a fantasy. It is a choice that many cities have already \
made. The evidence points in one direction: fewer cars downtown means cleaner air, safer \
streets, and better use of public space.""",
    ),
    (
        "S05",
        "Aisha Patel",
        """I believe cities should ban private cars downtown. A ban would reduce air pollution and \
traffic deaths, and it would make downtown a more pleasant place to spend time.

The strongest evidence comes from cities that have already tried it. According to the European \
Environment Agency, low-emission zones in more than 200 cities have lowered nitrogen dioxide \
levels. In Stockholm, traffic dropped by about 20 percent during the first years of its \
congestion charge and car restrictions. That is a real, measured change, not a guess.

Safety matters too. When cars move slowly, pedestrians survive crashes more often. A study by \
the Insurance Institute for Highway Safety found that a 5 mile per hour reduction in speed \
limits reduced fatal crashes by roughly 30 percent in some areas. A downtown ban goes even \
further by keeping most cars out entirely.

However, there is a serious counterargument. Many people cannot afford to live downtown and \
must drive to work. If the city bans cars without providing buses, those workers will lose their \
jobs or spend hours commuting. The policy could also hurt disabled residents who need a vehicle.

To address this, the city should expand bus routes, build protected bike lanes, and offer \
permits for people with disabilities. Delivery trucks should be allowed in the early morning. A \
phased approach would give residents time to adjust.

In conclusion, the benefits of a car-free downtown are worth the effort. Cleaner air and safer \
streets are public goods that everyone shares. If the city plans carefully, a ban can be fair as \
well as effective.""",
    ),
    (
        "S06",
        "Liam O'Connor",
        """Cities should think carefully before banning cars downtown, but I think a ban is the \
right choice. Cars cause pollution and accidents, and downtowns are better when they are built \
for people.

One reason is pollution. Car exhaust creates smog and makes asthma worse. According to the \
American Lung Association, nearly four in ten Americans live in places with unhealthy air. \
Downtown areas have some of the worst air because traffic is concentrated there. Fewer cars \
would mean fewer health problems.

Another reason is safety. Drivers often speed on wide downtown streets, and pedestrians are at \
risk. If cars are banned, people can walk and bike without worrying about being hit. Cities like \
Copenhagen have shown that this can work.

Some people say a ban would hurt businesses because customers could not park. But stores in \
walkable areas often do better. People who walk stop at more shops, and the city can still allow \
delivery trucks. The ban does not have to be total; it can apply only to private cars during \
busy hours.

A ban could be hard for people who live far away or have disabilities. The city should provide \
buses and permits so those groups are not left behind. Without that, the policy would be unfair.

Overall, a downtown car ban is a good idea if it is done carefully. It would improve air quality \
and safety and make the city more enjoyable for everyone.""",
    ),
    (
        "S07",
        "Sofia Rossi",
        """Should downtowns ban cars? I think they should, because cars create pollution and take \
up too much space.

According to the EPA, transportation is a major source of greenhouse gases. In downtown areas, \
traffic is often bumper to bumper, which means cars are burning fuel and releasing pollution \
into the air where people walk. If the city removed private cars, the air would be cleaner, and \
people with asthma would breathe easier.

Cars also cause accidents. A pedestrian hit by a car can be seriously injured or killed. \
Narrow streets and lots of pedestrians make downtown dangerous. A ban would make it safer for \
people to walk, bike, and shop.

Some people argue that businesses need cars to bring customers. However, studies show that \
walkable shopping areas can be successful. When customers walk, they might visit more stores. \
The city can still allow delivery trucks at certain times.

There is also a fairness issue. Not everyone can take the bus, and some people need cars. The \
city should make sure buses run often and allow people with disabilities to drive downtown. If \
those steps are taken, the ban would be fairer.

In conclusion, banning cars downtown would make the air cleaner and the streets safer. Cities \
should do it, but they should also help the people who depend on cars.""",
    ),
    (
        "S08",
        "Noah Williams",
        """I think cities should ban cars downtown. Cars are bad for the environment, and they make \
the streets dangerous.

First, cars cause pollution. A lot of cars driving in one area creates smog. According to the \
World Health Organization, air pollution causes millions of deaths every year. If we ban cars, \
the air would be cleaner and people would be healthier.

Second, streets would be safer. Drivers sometimes do not pay attention, and pedestrians get hit. \
If there are no cars, there cannot be car accidents downtown. That seems like a simple solution.

Third, there would be more space. Parking lots could become parks or buildings. This would make \
downtown nicer and maybe cheaper to live in.

Some people will say that banning cars is inconvenient. They might be right, but the city can \
add more buses and bike lanes. People can also walk more, which is good exercise. Businesses \
might worry about customers, but walkable areas can be popular.

In conclusion, a car ban downtown has more benefits than problems. It would help the environment \
and safety, and it would make downtown a better place. Cities should try it.""",
    ),
    (
        "S09",
        "Grace Kim",
        """Cities should ban private cars from downtown. There are three main reasons: pollution, \
safety, and space.

Cars produce a lot of pollution. According to the EPA, transportation causes about 29 percent of \
greenhouse gas emissions in the United States. When many cars drive in a small downtown area, \
the pollution is concentrated. This is bad for the people who live and work there. Banning cars \
would reduce the pollution.

Cars are also dangerous. Pedestrians and bikers can get hit by cars. If downtown has no cars, \
then people can walk safely. There would be fewer accidents and injuries.

Finally, cars take up space. Downtowns have many parking lots, which are ugly and empty. If we \
remove cars, we can build housing or parks instead. This would make downtown more lively.

Some people argue that a ban would hurt businesses and people who need to drive. These are valid \
concerns. The city should add buses and allow delivery trucks and disabled drivers. Then the ban \
would be more fair.

In conclusion, banning cars downtown would reduce pollution, improve safety, and create better \
public space. It is a good idea if the city plans for the people who need help.""",
    ),
    (
        "S10",
        "Diego Alvarez",
        """Downtown areas should ban cars. I have three reasons for this opinion.

First, cars pollute the air. It is a fact that cars release carbon dioxide. This is bad for \
climate change. If we stop cars downtown, the city will be cleaner. People will be more healthy.

Second, cars are dangerous to pedestrians. Many people die from car accidents every year. \
Downtown is crowded, so it is risky. With no cars, walking will be safe.

Third, there will be more room. Parking lots take up space. We could use the space for houses or \
stores. This will help the city grow.

Some people might say that driving is convenient. Also businesses need customers. But buses can \
replace cars. And walkers spend money too. So the problems are not big.

In conclusion, banning cars downtown is a good idea. It will help the environment, safety, and \
the city. Cities should do this soon.""",
    ),
    (
        "S11",
        "Hannah Schmidt",
        """I think downtown should ban cars because it is better for the environment and for people.

Cars make pollution. There is a lot of traffic downtown every day. This makes the air bad. If \
the cars are gone the air will be better. Also it will help with climate change because cars \
make carbon.

Another thing is safety. Cars can hit people. Downtown has many people walking so a car could \
hurt someone. If we ban cars then there will be no accidents. This is good.

Also there will be more space for parks and shops. Parking lots are ugly. We can build something \
better there.

But some people need cars. Like old people or people who live far. The city should give them a \
bus. Also delivery trucks should come in the morning.

In conclusion I think banning cars is good. It will make downtown better for everyone and safer. \
The city should try it and see what happens.""",
    ),
    (
        "S12",
        "Tyler Brooks",
        """Downtown should ban cars. Cars are bad and they cause problems.

First cars pollute the air and this is bad for people. There is too much traffic downtown and \
the air smells. If cars are banned the air would be clean. Also cars cause global warming.

Second cars hit people. I saw a car almost hit someone downtown. If there are no cars this would \
not happen. It is safer for walking.

Some people like cars because they are fast. But walking is also good exercise. Businesses might \
lose money but maybe not.

I think the city should ban cars because it is better for everyone. It will make downtown nicer \
and cleaner.""",
    ),
    (
        "S13",
        "Mei Lin",
        """I think cars should be banned downtown. Because cars are dangerous and they pollute.

Cars pollute the air with smoke. Downtown has a lot of cars so the air is bad. People with asthma \
have problems. If there are no cars they will feel better. Also it causes climate change.

Cars can hit people and hurt them. Downtown is busy so this can happen. A ban would make it safe \
for walking and biking.

Some people need cars to get to work. But the city can have buses. Also delivery trucks can come \
early before people are there.

So I think a ban is good. It will help the air and safety. The city should do it.""",
    ),
    (
        "S14",
        "Omar Hassan",
        """Cars should be banned downtown. It is a good idea for the city.

First, cars are polluting the air. If there is no cars downtown, the air will be better. This is \
good for health.

Second, it will be safer. Cars hit people. With no cars people can walk.

Third, there will be more space. Parking lots are a waste. We can build houses.

Some people need cars but they can take the bus. The city should add more buses.

In conclusion I think banning cars is good. The city should do it.""",
    ),
    (
        "S15",
        "Ruby Johnson",
        """I think cities should ban cars downtown because cars make pollution and they are dangerous. \
Also downtown would be more quiet. People could walk and shop. The city should add buses for \
people who need them. This is why I think cars should be banned.""",
    ),
    (
        "S16",
        "Sam Turner",
        """Cars are bad for the city. They pollute and cause accidents. We should ban them downtown so \
people can walk safely. That is my opinion.""",
    ),
    (
        "S17",
        "Nina Petrova",
        """Basketball is the best sport in the world. My favorite team is the Lakers because they have \
a great history and they always try to win. According to sports reporters, the Lakers have won \
many championships over the years.

I like basketball because it is fast and exciting. Players can score a lot of points and the \
crowd gets loud. The games are fun to watch with friends and family. There are also good \
players who work hard.

Some people prefer football, but basketball is better because the games are shorter. A basketball \
game only takes two hours. Football games take longer and have many stops.

In conclusion, basketball is a great sport and everyone should watch it. The Lakers are my \
favorite team.""",
    ),
    (
        "S18",
        "Caleb Wright",
        """Video games are the best. I play them every day after school. My favorite game is a shooter \
game and it is very fun. Some people say video games are bad for you but they are wrong.

First, video games help with hand eye coordination. Also they are fun and you can play with \
friends online. There are many games to choose from.

In conclusion video games are good and everyone should play them.""",
    ),
    (
        "S19",
        "Leila Haddad",
        """Downtown should ban private cars. This would help the environment and make the city safer.

According to some studies, cars cause a lot of pollution. The air downtown is not good. If we ban \
cars, people will breathe better. Also it will help with climate change.

Cars are also dangerous. Pedestrians can get hit. Downtown has many people, so it is a problem. A \
ban would make it safer for everyone.

However, some people need their cars. The city should have buses and allow disabled people to \
drive. Delivery trucks also need to come.

In conclusion, banning cars downtown is a good idea. It will help the environment and safety. The \
city should do it.""",
    ),
    (
        "S20",
        "Ben Foster",
        """I think downtowns should ban cars. The main reason is pollution. According to the EPA, \
transportation is a big source of emissions. Downtown traffic makes it worse because cars are \
close together.

Another reason is safety. Pedestrians get hit by cars, and downtown is where a lot of people \
walk. If cars are gone, the streets are safer.

Some people will say businesses need cars to bring customers. But customers can take the bus or \
walk. The city can also keep delivery trucks.

Overall, a car ban downtown is a good idea. The city should add buses first so people can still \
get around.""",
    ),
    (
        "S21",
        "Chloe Dubois",
        """Downtowns should ban private cars, and the sooner the better. The policy is popular, \
practical, and proven.

The evidence is not hard to find. According to the Clean Cities Campaign, over 300 European \
cities have restricted cars in their centers, and many have seen nitrogen dioxide drop by 20 to \
30 percent. In Paris, car traffic in the center fell by roughly 45 percent after restrictions and \
bike lane investments. These results matter because downtown air pollution is concentrated where \
people walk, eat, and send their children to school.

Safety is the second argument. Traffic violence kills more than a million people worldwide each \
year, according to the World Health Organization. Speed is the key variable: a pedestrian struck \
at 30 miles per hour is more than five times as likely to die as one struck at 20. Removing cars \
from the busiest blocks removes the risk almost entirely.

Critics respond that bans hurt workers and businesses. The business objection is weaker than it \
sounds. A study of pedestrian zones in New York found that retail sales rose after streets were \
closed to cars, and delivery windows keep shelves stocked. The equity objection is stronger: \
people who cannot afford downtown housing or who have disabilities need alternatives. A good ban \
funds frequent buses, protects bike lanes, and grants accessible permits before enforcement \
begins.

A city is not a highway with buildings attached. It is a place where people should be able to \
walk without fear and breathe without hurting. Banning private cars downtown is the clearest way \
to make that vision real, provided the city builds transit first and phases enforcement \
honestly.""",
    ),
    (
        "S22",
        "Raj Malhotra",
        """Cities should ban private cars in downtown areas. Pollution and safety are the biggest \
reasons.

According to the EPA, cars produce a large share of greenhouse gases. Downtown traffic is \
concentrated, so pollution is worse there. A ban would reduce asthma and other health problems.

Cars also cause crashes. Pedestrians are at risk, especially children and older people. If the \
streets are car-free, walking becomes much safer.

Some people need cars to get to work. The city should expand buses and allow permits for people \
with disabilities. Delivery trucks can come early in the morning.

In conclusion, a downtown car ban is worth doing. It would improve health and safety, and with \
good transit it could be fair for everyone.""",
    ),
    (
        "S23",
        "Emma Larsen",
        """I think cars should be banned downtown. Cars are bad for the environment.

Cars make pollution and it is bad. The air downtown is dirty from all the cars. If we ban cars \
the air will be cleaner and people will be healthy.

Also cars are dangerous. They can hit people walking. A ban would stop this.

Some people say it is unfair but the city can make buses. So I think we should ban cars \
downtown. It is a good idea.""",
    ),
    (
        "S24",
        "Victor Nunes",
        """Cars should be banned downtown. They pollute the air and cause accidents. Without cars, \
people can walk safely and the city will be cleaner. That is why I support a ban.""",
    ),
]


def seed(
    session_factory: sessionmaker[Session] | None = None,
) -> dict[str, int]:
    factory = session_factory or SessionLocal
    with factory() as session:
        existing = session.scalars(select(Course).where(Course.name == COURSE_NAME)).first()
        if existing is not None:
            session.delete(existing)
            session.commit()

        # Keep `make seed` byte-for-byte reproducible for a demo database: when no
        # courses remain, restart identity sequences so the assignment is always #1.
        if session.scalars(select(Course)).first() is None:
            for table in Base.metadata.sorted_tables:
                session.execute(
                    text("SELECT setval(pg_get_serial_sequence(:table, 'id'), 1, false)"),
                    {"table": table.name},
                )
            session.commit()

        course = Course(name=COURSE_NAME)
        session.add(course)
        session.flush()

        assignment = Assignment(
            course_id=course.id,
            title=ASSIGNMENT_TITLE,
            prompt_text=PROMPT_TEXT,
            max_points=sum(item[2] for item in RUBRIC),
        )
        assignment.criteria = [
            RubricCriterion(
                name=name,
                description=description,
                max_points=max_points,
                weight=weight,
                order_index=index,
            )
            for index, (name, description, max_points, weight) in enumerate(RUBRIC)
        ]
        session.add(assignment)
        session.flush()

        base_time = datetime.now(UTC) - timedelta(days=9)
        for index, (external_id, name, essay) in enumerate(STUDENTS):
            student = Student(course_id=course.id, external_id=external_id, name=name)
            session.add(student)
            session.flush()
            session.add(
                Submission(
                    assignment_id=assignment.id,
                    student_id=student.id,
                    text=essay,
                    submitted_at=base_time + timedelta(hours=index * 5),
                )
            )

        session.commit()

        print(f"Seeded course #{course.id}: {COURSE_NAME}")
        print(f"Assignment #{assignment.id}: {ASSIGNMENT_TITLE}")
        print(f"Rubric criteria: {len(RUBRIC)} (max {assignment.max_points:g} points)")
        print(f"Students/submissions: {len(STUDENTS)}")
        print("Gold labels: eval/data/gold_scores.json (read by the offline eval harness)")
        return {"course_id": course.id, "assignment_id": assignment.id}


if __name__ == "__main__":
    seed()
